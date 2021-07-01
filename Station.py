from PyQt5.QtGui import QBrush, QPen, QColor
from PyQt5.QtCore import Qt
from Borders import ColliderLine


class Station:
    def __init__(self, posX, posY, radius, color, scaleFactor):
        self.scaleFactor = scaleFactor
        self.posX = posX
        self.posY = posY

        self.radius = radius

        # self.color = Qt.blue
        # if color == 1:
        #     self.color = Qt.red
        # if color == 2:
        #     self.color = Qt.darkGray
        # if color == 3:
        #     self.color = Qt.green
        # if color == 4:
        #     self.color = Qt.darkBlue
        # if color == 5:
        #     self.color = Qt.gray


        brightness = 235 - (int((color * 39) / 255) * 80)
        self.color = QColor.fromHsv((color * 39) % 255, 255, brightness)

        self.lineColor = self.color  # Qt.red Qt.blue
        self.fillColor = self.color  # Qt.red Qt.blue

        self.thickness = 2
        self.lineStyle = Qt.SolidLine
        self.brushStyle = Qt.SolidPattern



    # def __init__(self, posX, posY, width, length, color, scaleFactor):
    #     self.scaleFactor = scaleFactor
    #     self.posX = posX
    #     self.posY = posY
    #
    #     self.width = width
    #     self.length = length
    #
    #     self.color = Qt.blue
    #     if color == 1:
    #         self.color = Qt.red
    #     if color == 2:
    #         self.color = Qt.yellow
    #     if color == 3:
    #         self.color = Qt.green
    #     if color == 4:
    #         self.color = Qt.darkBlue
    #     if color == 5:
    #         self.color = Qt.gray
    #
    #
    #     self.lineColor = self.color  # Qt.red Qt.blue
    #     self.fillColor = self.color  # Qt.red Qt.blue
    #
    #     self.thickness = 2
    #     self.lineStyle = Qt.SolidLine
    #     self.brushStyle = Qt.SolidPattern
    #
    #     self.borders = [ColliderLine(posX+width, posY, posX, posY),
    #                     ColliderLine(posX, posY, posX, posY+length),
    #                     ColliderLine(posX, posY+length, posX+width, posY+length),
    #                     ColliderLine(posX+width, posY+length, posX+width, posY)]


    def paint(self, painter):
        painter.setPen(QPen(self.lineColor, self.thickness, self.lineStyle))
        painter.setBrush(QBrush(self.fillColor, self.brushStyle))
        painter.drawEllipse((self.posX-self.radius) * self.scaleFactor, (self.posY-self.radius) * self.scaleFactor, self.radius*2 * self.scaleFactor, self.radius*2 * self.scaleFactor)
        # painter.drawRect(self.posX * self.scaleFactor, self.posY * self.scaleFactor, self.width * self.scaleFactor, self.length * self.scaleFactor)

    def setPos(self, pos):
        self.posX, self.posY = pos

    def getPosX(self):
        return self.posX

    def getPosY(self):
        return self.posY

    def getWidth(self):
        """
        only for rectangular Stations
        :return: float station width in meter
        """
        return self.width

    def getLength(self):
        """
        only for rectangular Stations
        :return: float station length in meter
        """
        return self.length

    def getRadius(self):
        return self.radius

    def updateScale(self, scaleFactor):
        self.scaleFactor = scaleFactor
