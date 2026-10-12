"""XRL-Editor mit Zeilennummern und sichtbaren Haltepunkten."""
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QPlainTextEdit, QWidget


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setToolTip('Klick: Haltepunkt vor dieser Zeile setzen oder entfernen (F9)')

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)

    def mousePressEvent(self, event):
        block = self.editor.firstVisibleBlock()
        top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
        while block.isValid():
            height = self.editor.blockBoundingRect(block).height()
            if top <= event.position().y() < top + height:
                self.editor.toggle(block.blockNumber() + 1)
                return
            top += height
            block = block.next()


class CodeEditor(QPlainTextEdit):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.gutter = Gutter(self)
        self.setAccessibleName('XRL-Programm mit Zeilennummern und Haltepunkten')
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.update_margin()

    def gutter_width(self):
        return 24 + self.fontMetrics().horizontalAdvance('9') * max(3, len(str(self.blockCount())))

    def update_margin(self, *args):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def toggle(self, line=None):
        line = line or self.textCursor().blockNumber() + 1
        points = self.win.sim.active.breakpoints
        points.remove(line) if line in points else points.add(line)
        self.gutter.update()
        self.win.mark_changed()

    def paint_gutter(self, event):
        p = QPainter(self.gutter)
        p.fillRect(event.rect(), QColor('#0a1830'))
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        points = self.win.sim.active.breakpoints
        current = self.win.sim.cur_line
        while block.isValid() and top <= event.rect().bottom():
            height = self.blockBoundingRect(block).height()
            number = block.blockNumber() + 1
            if block.isVisible() and top + height >= event.rect().top():
                if number in points:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor('#ff6b81'))
                    p.drawEllipse(QRect(4, int(top + height / 2 - 4), 8, 8))
                p.setPen(QColor('#52b7ff' if number == current else '#879cba'))
                p.drawText(17, int(top), self.gutter.width() - 22, int(height), Qt.AlignmentFlag.AlignRight, str(number))
            block = block.next()
            top += height
