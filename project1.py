import sys
import os
import tempfile

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QListWidget, QFileDialog, QMessageBox, QHBoxLayout,
    QProgressBar, QLabel, QLineEdit, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QSettings
from PyQt5.QtGui import QDesktopServices

from PyPDF2 import PdfMerger, PdfReader, PdfWriter


# ---------------- WORKER THREAD ----------------
class MergeWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, files, output, excluded_pages):
        super().__init__()
        self.files = files
        self.output = output
        self.excluded_pages = excluded_pages

    def run(self):
        try:
            writer = PdfWriter()
            current_page = 1
            total_files = len(self.files)

            for i, pdf in enumerate(self.files):
                reader = PdfReader(pdf)

                for page in reader.pages:
                    if current_page not in self.excluded_pages:
                        writer.add_page(page)
                    current_page += 1

                percent = int(((i + 1) / total_files) * 100)
                self.progress.emit(percent, f"Merging file {i + 1} of {total_files}")

            with open(self.output, "wb") as f:
                writer.write(f)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


# ---------------- MAIN APP ----------------
class PdfMergerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Merger")
        self.resize(700, 520)
        self.setAcceptDrops(True)

        self.settings = QSettings("PdfMergerApp", "Settings")

        self.temp_preview_files = []
        self.excluded_pages = set()

        # ---------- UI ----------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setMinimumHeight(260)
        self.list_widget.itemDoubleClicked.connect(self.preview_merged)

        layout.addWidget(self.list_widget)

        # Page removal
        page_layout = QHBoxLayout()
        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText("Remove pages (e.g. 2,5,8-10)")
        self.apply_pages_btn = QPushButton("Apply")
        self.apply_pages_btn.clicked.connect(self.apply_page_removal)

        page_layout.addWidget(QLabel("Remove pages:"))
        page_layout.addWidget(self.page_input)
        page_layout.addWidget(self.apply_pages_btn)
        layout.addLayout(page_layout)

        # Info
        info_layout = QHBoxLayout()
        self.page_count_label = QLabel("Total pages: 0")
        self.progress_text = QLabel("")
        info_layout.addWidget(self.page_count_label)
        info_layout.addStretch()
        info_layout.addWidget(self.progress_text)
        layout.addLayout(info_layout)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add PDFs")
        self.remove_btn = QPushButton("Remove Selected")
        self.preview_btn = QPushButton("Preview")
        self.merge_btn = QPushButton("Merge PDFs")
        self.open_folder_cb = QCheckBox("Open folder after merge")

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.preview_btn)
        btn_layout.addWidget(self.merge_btn)
        btn_layout.addWidget(self.open_folder_cb)

        layout.addLayout(btn_layout)

        # Signals
        self.add_btn.clicked.connect(self.add_files)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.preview_btn.clicked.connect(self.preview_merged)
        self.merge_btn.clicked.connect(self.merge_pdfs)

        self.update_buttons()

    # ---------- Drag & Drop ----------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.add_pdf(path)

    # ---------- Utilities ----------
    def add_pdf(self, path):
        pages = len(PdfReader(path).pages)
        self.list_widget.addItem(f"{path}   [{pages} pages]")
        self.update_page_count()
        self.update_buttons()

    def get_files(self):
        return [
            self.list_widget.item(i).text().split("   [")[0]
            for i in range(self.list_widget.count())
        ]

    def update_page_count(self):
        total = 0
        for f in self.get_files():
            total += len(PdfReader(f).pages)
        total -= len(self.excluded_pages)
        self.page_count_label.setText(f"Total pages: {max(total,0)}")

    def update_buttons(self):
        enabled = self.list_widget.count() >= 2
        self.preview_btn.setEnabled(enabled)
        self.merge_btn.setEnabled(enabled)

    # ---------- Page removal ----------
    def apply_page_removal(self):
        self.excluded_pages.clear()
        text = self.page_input.text().replace(" ", "")

        if not text:
            self.update_page_count()
            return

        try:
            for part in text.split(","):
                if "-" in part:
                    a, b = map(int, part.split("-"))
                    self.excluded_pages.update(range(a, b + 1))
                else:
                    self.excluded_pages.add(int(part))
            self.update_page_count()
        except Exception:
            QMessageBox.warning(self, "Error", "Invalid page range format")

    # ---------- Preview ----------
    def preview_merged(self):
        if self.list_widget.count() < 2:
            return

        try:
            writer = PdfWriter()
            current_page = 1

            for pdf in self.get_files():
                reader = PdfReader(pdf)
                for page in reader.pages:
                    if current_page not in self.excluded_pages:
                        writer.add_page(page)
                    current_page += 1

            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            writer.write(temp.name)
            self.temp_preview_files.append(temp.name)

            QDesktopServices.openUrl(QUrl.fromLocalFile(temp.name))

        except Exception as e:
            QMessageBox.critical(self, "Preview Error", str(e))

    # ---------- Buttons ----------
    def add_files(self):
        last_dir = self.settings.value("last_dir", "")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select PDFs", last_dir, "PDF Files (*.pdf)"
        )
        if files:
            self.settings.setValue("last_dir", os.path.dirname(files[0]))
        for f in files:
            self.add_pdf(f)

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self.update_page_count()
        self.update_buttons()

    def merge_pdfs(self):
        last_dir = self.settings.value("last_dir", "")
        output, _ = QFileDialog.getSaveFileName(
            self, "Save Merged PDF", last_dir, "PDF Files (*.pdf)"
        )
        if not output:
            return

        self.worker = MergeWorker(
            self.get_files(), output, self.excluded_pages
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(lambda: self.merge_done(output))
        self.worker.error.connect(self.merge_error)
        self.worker.start()

    def on_progress(self, value, text):
        self.progress.setValue(value)
        self.progress_text.setText(text)

    def merge_done(self, output):
        self.progress.setValue(0)
        self.progress_text.setText("")
        QMessageBox.information(self, "Success", "PDFs merged successfully!")

        if self.open_folder_cb.isChecked():
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.dirname(output))
            )

    def merge_error(self, msg):
        QMessageBox.critical(self, "Error", msg)

    # ---------- Cleanup ----------
    def closeEvent(self, event):
        for f in self.temp_preview_files:
            try:
                os.remove(f)
            except Exception:
                pass
        event.accept()


# ---------------- RUN ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PdfMergerApp()
    window.show()
    sys.exit(app.exec_())
