"""Small Qt helpers shared by the laboratory windows."""
from datetime import datetime
import math

from PySide6.QtCore import QObject, QRunnable, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QLineEdit,
    QTableWidget, QTableWidgetItem,
)

_jobs = set()


class _Signals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            result = self.function()
        except Exception as error:
            self.signals.failed.emit(str(error))
        else:
            self.signals.finished.emit(result)


def run_job(pool, function, success, error):
    worker = Worker(function)
    # Retain the signal owner until its queued result reaches the GUI thread.
    _jobs.add(worker)
    worker.signals.finished.connect(success)
    worker.signals.failed.connect(error)
    worker.signals.finished.connect(lambda _: _jobs.discard(worker))
    worker.signals.failed.connect(lambda _: _jobs.discard(worker))
    pool.start(worker)
    return worker


def style(app):
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow { background: #eef2f6; }
        QGroupBox { background: white; border: 1px solid #d2dce7;
            border-radius: 7px; margin-top: 13px; padding: 12px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
        QPushButton { padding: 7px 12px; border: 1px solid #b7c6d7;
            border-radius: 5px; background: #f8fafc; }
        QPushButton:hover { background: #e5eef8; }
        QPushButton:disabled { color: #8e99a8; }
        QPushButton[primary="true"] { background: #185c95; color: white; }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { padding: 5px; }
        QTableWidget { background: white; gridline-color: #e2e8f0; }
        QHeaderView::section { background: #e6edf5; padding: 7px; border: 0; }
        QPlainTextEdit { background: #142331; color: #dbe9f5; border-radius: 5px; }
    """)


def make_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    return table


def fill_table(table, rows):
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(str(value)))


def log_append(log, text):
    for line in str(text).splitlines():
        log.appendPlainText(f"{datetime.now().astimezone():%H:%M:%S}  {line}")


class NumericEdit(QLineEdit):
    """Preserve the complete double range, including scientific notation.

    Fixed decimal spinboxes round narrow but valid JSON ranges to zero. Parse
    on submission instead; the shared point validator reports bounds errors.
    """
    def setValue(self, value):
        self.setText(format(float(value), ".17g"))

    def value(self):
        try:
            value = float(self.text().strip())
        except ValueError as error:
            raise ValueError("Nombre attendu, par exemple 30.5 ou 1e-8.") from error
        if not math.isfinite(value):
            raise ValueError("Une valeur numérique finie est requise.")
        return value


def value_editor(point, parent=None):
    if point["dnp3_type"] in ("BI", "BO"):
        widget = QComboBox(parent)
        widget.addItem("OFF / false", False)
        widget.addItem("ON / true", True)
        widget.setCurrentIndex(int(bool(point.get("initial", False))))
        return widget
    widget = NumericEdit(parent)
    initial = float(point.get("initial", 0))
    widget.setValue(max(float(point.get("min", -math.inf)), min(float(point.get("max", math.inf)), initial)))
    widget.setToolTip(f"{point['name']} · {point.get('unit', '')} · notation scientifique acceptée")
    if point["dnp3_type"] == "AO":
        widget.setPlaceholderText(f"{point['min']} … {point['max']} {point.get('unit', '')}")
    widget.setMinimumWidth(150)
    return widget


def editor_value(widget):
    if isinstance(widget, QComboBox):
        return widget.currentData()
    value = widget.value()
    if not math.isfinite(value):
        raise ValueError("Une valeur numérique finie est requise.")
    return value
