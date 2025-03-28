#!/usr/bin/env python3
"""
Ollama Ideation UI - A GUI for batch ideation using Ollama's API
"""
import sys
import os
import json
import threading
import queue
import time
import re
import requests
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox, QFileDialog,
    QSpinBox, QProgressBar, QGroupBox, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor

# Constants
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:latest"

class OllamaIdeationWorker(QThread):
    """Worker thread for generating ideas using Ollama API"""
    progress_updated = pyqtSignal(int)
    output_received = pyqtSignal(str)
    idea_generated = pyqtSignal(str, str)  # filename, content
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, prompt_template, batch_size, output_folder):
        super().__init__()
        self.prompt_template = prompt_template
        self.batch_size = batch_size
        self.output_folder = output_folder
        self.is_running = True

    def run(self):
        """Run the ideation process"""
        try:
            os.makedirs(self.output_folder, exist_ok=True)
            
            for i in range(self.batch_size):
                if not self.is_running:
                    break
                
                # Create the full prompt with system instructions
                system_prompt = (
                    "You are a creative ideation assistant. Generate unique and varied ideas. "
                    "Avoid repetition and maximize variability between iterations. "
                    "Your response should be in markdown format. "
                    "The filename should be a concise summary of the idea (max 50 chars)."
                )
                
                prompt = {
                    "model": MODEL,
                    "prompt": self.prompt_template,
                    "system": system_prompt,
                    "stream": False
                }
                
                self.output_received.emit(f"Generating idea {i+1}/{self.batch_size}...\n")
                
                # Call Ollama API
                try:
                    response = requests.post(OLLAMA_API_URL, json=prompt)
                    response.raise_for_status()
                    result = response.json()
                    idea_content = result.get("response", "")
                    
                    # Extract a filename from the idea content
                    idea_title = self._extract_title(idea_content)
                    sanitized_title = self._sanitize_filename(idea_title)
                    
                    # Save the idea to a file
                    filename = f"{sanitized_title}.md"
                    filepath = os.path.join(self.output_folder, filename)
                    
                    # Ensure filename is unique
                    counter = 1
                    while os.path.exists(filepath):
                        filename = f"{sanitized_title}_{counter}.md"
                        filepath = os.path.join(self.output_folder, filename)
                        counter += 1
                    
                    with open(filepath, 'w') as f:
                        f.write(idea_content)
                    
                    self.idea_generated.emit(filename, idea_content)
                    self.output_received.emit(f"Saved idea to: {filepath}\n")
                    
                except requests.RequestException as e:
                    self.error_occurred.emit(f"API Error: {str(e)}")
                    time.sleep(2)  # Wait before retrying
                
                # Update progress
                self.progress_updated.emit(int((i + 1) / self.batch_size * 100))
                
                # Small delay to prevent overwhelming the API
                time.sleep(0.5)
            
            self.output_received.emit(f"\nCompleted generating {self.batch_size} ideas!\n")
            self.finished.emit()
            
        except Exception as e:
            self.error_occurred.emit(f"Error: {str(e)}")
            self.finished.emit()

    def stop(self):
        """Stop the ideation process"""
        self.is_running = False
        self.wait()

    def _extract_title(self, content):
        """Extract a title from the idea content"""
        # Try to find a heading
        heading_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if heading_match:
            return heading_match.group(1).strip()[:50]
        
        # Otherwise take the first line
        first_line = content.strip().split('\n')[0]
        return first_line[:50]

    def _sanitize_filename(self, filename):
        """Sanitize the filename to be valid"""
        # Remove invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        sanitized = sanitized.replace(' ', '_')
        # Ensure it's not empty
        if not sanitized:
            sanitized = f"idea_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return sanitized


class MainWindow(QMainWindow):
    """Main application window"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ollama Ideation UI")
        self.resize(800, 600)
        self.worker = None
        
        self.init_ui()
        
    def init_ui(self):
        """Initialize the UI components"""
        # Main layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Create a splitter for resizable sections
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)
        
        # Top section - Configuration
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        
        # Prompt input
        prompt_group = QGroupBox("Ideation Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        
        prompt_label = QLabel("Enter your ideation prompt:")
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Example: Generate an idea for a consumer information app that leverages AI...")
        self.prompt_input.setMinimumHeight(100)
        
        prompt_layout.addWidget(prompt_label)
        prompt_layout.addWidget(self.prompt_input)
        
        # Batch size selection
        batch_group = QGroupBox("Batch Settings")
        batch_layout = QHBoxLayout(batch_group)
        
        batch_label = QLabel("Batch Size:")
        self.batch_combo = QComboBox()
        self.batch_combo.addItems(["100", "200", "500", "1000", "10000", "Custom"])
        self.batch_combo.currentTextChanged.connect(self.on_batch_size_changed)
        
        self.custom_batch = QSpinBox()
        self.custom_batch.setRange(1, 100000)
        self.custom_batch.setValue(100)
        self.custom_batch.setEnabled(False)
        
        batch_layout.addWidget(batch_label)
        batch_layout.addWidget(self.batch_combo)
        batch_layout.addWidget(self.custom_batch)
        batch_layout.addStretch()
        
        # Output folder selection
        output_group = QGroupBox("Output Settings")
        output_layout = QHBoxLayout(output_group)
        
        output_label = QLabel("Output Folder:")
        self.output_path = QLineEdit()
        self.output_path.setText(os.path.expanduser("~/ideation_output"))
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_output_folder)
        
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(browse_button)
        
        # Add configuration widgets to layout
        config_layout.addWidget(prompt_group)
        config_layout.addWidget(batch_group)
        config_layout.addWidget(output_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Ideation")
        self.start_button.clicked.connect(self.start_ideation)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_ideation)
        self.stop_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        
        config_layout.addLayout(button_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        config_layout.addWidget(self.progress_bar)
        
        # Bottom section - Terminal output
        terminal_group = QGroupBox("Terminal Output")
        terminal_layout = QVBoxLayout(terminal_group)
        
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setFont(QFont("Monospace", 10))
        self.terminal.setStyleSheet("background-color: #2b2b2b; color: #f0f0f0;")
        
        terminal_layout.addWidget(self.terminal)
        
        # Add widgets to splitter
        splitter.addWidget(config_widget)
        splitter.addWidget(terminal_group)
        
        # Set initial splitter sizes
        splitter.setSizes([400, 200])
        
        self.setCentralWidget(main_widget)
        
        # Add initial message to terminal
        self.log_message(f"Ollama Ideation UI initialized. Using model: {MODEL}")
        self.log_message("Ready to start ideation. Configure your prompt and settings above.")
    
    def on_batch_size_changed(self, text):
        """Handle batch size combo box changes"""
        if text == "Custom":
            self.custom_batch.setEnabled(True)
        else:
            self.custom_batch.setEnabled(False)
    
    def browse_output_folder(self):
        """Open file dialog to select output folder"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", 
            self.output_path.text(), 
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.output_path.setText(folder)
    
    def get_batch_size(self):
        """Get the selected batch size"""
        batch_text = self.batch_combo.currentText()
        if batch_text == "Custom":
            return self.custom_batch.value()
        return int(batch_text)
    
    def start_ideation(self):
        """Start the ideation process"""
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            self.log_message("Error: Please enter an ideation prompt.")
            return
        
        batch_size = self.get_batch_size()
        output_folder = self.output_path.text()
        
        # Verify Ollama is running
        try:
            response = requests.get("http://localhost:11434/api/tags")
            if response.status_code != 200:
                self.log_message("Error: Ollama API is not responding. Make sure Ollama is running.")
                return
        except requests.RequestException:
            self.log_message("Error: Could not connect to Ollama API. Make sure Ollama is running.")
            return
        
        # Start the worker thread
        self.worker = OllamaIdeationWorker(prompt, batch_size, output_folder)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.output_received.connect(self.log_message)
        self.worker.idea_generated.connect(self.on_idea_generated)
        self.worker.error_occurred.connect(self.log_error)
        self.worker.finished.connect(self.on_ideation_finished)
        
        self.worker.start()
        
        # Update UI state
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.log_message(f"Starting ideation with batch size: {batch_size}")
        self.log_message(f"Output folder: {output_folder}")
    
    def stop_ideation(self):
        """Stop the ideation process"""
        if self.worker and self.worker.isRunning():
            self.log_message("Stopping ideation process...")
            self.worker.stop()
    
    def update_progress(self, value):
        """Update the progress bar"""
        self.progress_bar.setValue(value)
    
    def log_message(self, message):
        """Add a message to the terminal output"""
        self.terminal.append(message)
        # Auto-scroll to bottom
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)
    
    def log_error(self, error_message):
        """Log an error message with highlighting"""
        self.terminal.append(f"<span style='color: #ff6b6b;'>{error_message}</span>")
    
    def on_idea_generated(self, filename, content):
        """Handle when an idea is generated"""
        # Just log the filename, we don't need to display the full content
        self.log_message(f"Generated: {filename}")
    
    def on_ideation_finished(self):
        """Handle when the ideation process is finished"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.log_message("Ideation process completed.")


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
