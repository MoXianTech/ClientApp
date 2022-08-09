#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pyqtgraph.dockarea import *
import math
import sys
import time
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore
import threading
import serial
import serial.tools.list_ports
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
import datetime
from copy import deepcopy
from time import perf_counter
import sqlite3
from win32gui import FindWindow, ShowWindow
from win32con import SW_RESTORE
import pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5
import pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt5
import pyqtgraph.imageview.ImageViewTemplate_pyqt5

class CustomComboBox(QComboBox):
    popupAboutToBeShown = pyqtSignal()

    def __init__(self, parent = None):
        super(CustomComboBox,self).__init__(parent)

    # 重写showPopup函数
    def showPopup(self):
        # 先清空原有的选项
        self.clear()
        index = 0
        # 获取接入的所有串口信息，插入combobox的选项中
        portlist = self.get_port_list(self)
        if portlist is not None:
            for i in portlist:
                pos = i.find('-')
                self.insertItem(index, i[:pos-1])
                index += 1
        QComboBox.showPopup(self)   # 弹出选项框

    @staticmethod
    # 获取接入的所有串口号
    def get_port_list(self):
        try:
            port_list = list(serial.tools.list_ports.comports())
            for port in port_list:
                yield str(port)
        except Exception as e:
            print("获取接入的所有串口设备出错！\n错误信息："+str(e))

class MainWindow(QMainWindow):
    trans_data = pyqtSignal(dict)  # 创建信号

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)

        # 协议
        self.protocol_head = "a55a01"
        self.head_len = 6
        # 串口
        self.usable_port = []
        self.print_com()

        self.loop = True
        self.port = ''
        self.baud = 0
        self.start_btn_signal = True

        # 串口数据初始化
        self.receive_list = []
        self.matrix_list = []
        self.data_list = {}
        self.calibrate_copy = 0

        self.num_data = 0
        self.min_data = 0
        self.max_data = 0
        self.range_data = 0
        self.avg_data = 0
        self.mid_data = 0
        self.var_data = 0
        self.std_data = 0
        self.stop_signal = 0
        self.calibrate_signal = False   # True=打开校准；False=关闭校准
        self.data_type = 0   # 0=电压值；1=电阻值；2=重量值；3=压力值

        # 绘图数据初始化
        self.auto_map = False
        self.map_level = (0, 0)
        self.time_list = []
        self.avg_list = []
        self.last_time = 0
        self.row_num = 1
        self.col_num = 1
        self.resistance_num = 200
        self.voltage_num = 3.3
        self.internal_resistance = 0
        self.histogram_density = False

        # GUI
        self.area = DockArea()
        self.setCentralWidget(self.area)
        self.resize(1700, 900)
        self.setWindowTitle('墨现科技--客户端1.1.2')
        self.setWindowIcon(QIcon('matrix.png'))
        pg.setConfigOptions(antialias=True)

        # 设置Dock位置
        d1 = Dock("压力分布图", size=(700, 450), closable=True, fontSize=20)  ## give this dock the minimum possible size
        d2 = Dock("与时间关系图", size=(700, 450), closable=True, fontSize=20)
        d3 = Dock("一致性直方图", size=(700, 450), closable=True, fontSize=20)
        # d4 = Dock("与重量关系图", size=(700, 450), closable=True, fontSize=20)
        d5 = Dock("数据面板", size=(300, 600), fontSize=20)
        d6 = Dock("高级设置", size=(300, 600), fontSize=20)
        d7 = Dock("控制面板", size=(300, 300), fontSize=20)
        d8 = Dock("时间关系总览图", size=(700, 450), closable=True, fontSize=20)
        self.area.addDock(d1, 'left')
        self.area.addDock(d8, 'bottom', d1)
        self.area.addDock(d2, 'above', d8)
        # self.area.addDock(d3, 'right', d1)
        # self.area.addDock(d4, 'bottom', d2)
        self.area.addDock(d6, 'right')
        self.area.addDock(d5, 'above', d6)
        self.area.addDock(d7, 'bottom', d6)

        # Dock1--热力图
        pg.setConfigOption('imageAxisOrder', 'row-major')
        w1 = pg.GraphicsLayoutWidget()
        w1_view = w1.addViewBox()
        w1_view.setAspectLocked(True)
        w1_view.setMouseEnabled(x=False, y=False)
        self.img = pg.ImageItem(border='w')
        gray_map = pg.colormap.get(name='gray', source='matplotlib')
        self.bar = pg.ColorBarItem(interactive=False, colorMap=gray_map)
        self.bar.setImageItem(self.img)
        w1_view.addItem(self.img)
        # w1.addItem(self.bar)
        self.trans_data.connect(self.update_map)

        automap_checkbox = QCheckBox('自动调节显示区间')
        automap_checkbox.setCheckState(Qt.Unchecked)
        automap_checkbox.stateChanged.connect(self.automap_check)
        min_map_label = QLabel('最小值：')
        max_map_label = QLabel('最大值：')
        min_map_label.setAlignment(Qt.AlignCenter)
        max_map_label.setAlignment(Qt.AlignCenter)
        self.min_map = QDoubleSpinBox()
        self.max_map = QDoubleSpinBox()
        self.min_map.setRange(0, 100000)
        self.max_map.setRange(0, 100000)
        self.min_map.valueChanged.connect(self.update_mapLevel)
        self.max_map.valueChanged.connect(self.update_mapLevel)
        gray_radio = QRadioButton('灰阶图')
        jet_radio = QRadioButton('热力图')
        gray_radio.setChecked(True)
        self.d1_group = QButtonGroup()
        self.d1_group.addButton(gray_radio, 0)
        self.d1_group.addButton(jet_radio, 1)
        self.d1_group.buttonClicked[int].connect(self.mapColor_check)

        d1.addWidget(gray_radio, row=0, col=1)
        d1.addWidget(jet_radio, row=0, col=2)
        d1.addWidget(automap_checkbox, row=0, col=4)
        d1.addWidget(min_map_label, row=0, col=6)
        d1.addWidget(self.min_map, row=0, col=7)
        d1.addWidget(max_map_label, row=0, col=9)
        d1.addWidget(self.max_map, row=0, col=10)
        d1.addWidget(w1, row=1, col=0, colspan=11)

        # Dock2--随时间变化折线图
        self.w2 = pg.PlotWidget()
        self.w2.setLabel('bottom', '时间', 's')
        self.w2.showGrid(x=True, y=True)

        self.w2_data = []
        self.w2_time = -1
        self.w2_curve = self.w2.plot()
        self.w2_xPos = 0

        self.trans_data.connect(self.update_time)
        d2.addWidget(self.w2)

        # Dock8--随时间变化折线图 总览图
        self.w8 = pg.PlotWidget()
        self.w8.setLabel('bottom', '时间', 's')
        self.w8.setDownsampling(mode='peak')
        self.w8.setClipToView(True)
        self.w8.showGrid(x=True, y=True)

        self.w8_data = []
        self.w8_timeList = [0]
        self.w8_time = -1
        self.w8_curve = self.w8.plot()

        self.trans_data.connect(self.update_wholeTime)
        d8.addWidget(self.w8)


        # Dock3--直方图
        num_radio = QRadioButton('显示数量')
        density_radio = QRadioButton('显示比例')
        d3.addWidget(num_radio, row=0, col=4)
        d3.addWidget(density_radio, row=0, col=5)
        num_radio.setChecked(True)
        self.d3_group = QButtonGroup()
        self.d3_group.addButton(num_radio, 0)
        self.d3_group.addButton(density_radio, 1)
        self.d3_group.buttonClicked[int].connect(self.histogram_check)

        self.w3 = pg.PlotWidget()
        self.w3.showGrid(True, True)
        self.w3.setMouseEnabled(x=False, y=False)
        self.trans_data.connect(self.update_histogram)

        w3_label = pg.LabelItem(justify='right')
        self.w3.addItem(w3_label)
        d3.addWidget(self.w3, row=1, col=0, colspan=6)

        # Dock4--随压力变化折线图
        self.w4 = pg.PlotWidget()
        self.w4.setLabel('bottom', '质量', 'g')
        # self.w4_x = [20, 50, 100, 200, 500]
        self.w4_data1 = np.random.normal(size=100)
        self.w4_data2 = np.random.normal(size=100)
        self.w4_data3 = np.random.normal(size=100)
        # # res = curve_fit()
        # poly = np.polyfit(self.w4_x, self.w4_data3, deg=0)
        # z = np.polyval(poly, np.arange(20, 500))
        # self.w4_dict1 = dict(zip(self.w4_x, self.w4_data1))
        # self.w4_dict2 = dict(zip(self.w4_x, self.w4_data2))
        # self.w4_dict3 = dict(zip(np.arange(20, 500), z))
        self.w4.plot(self.w4_data1, pen="r")
        self.w4.plot(self.w4_data2, pen="g")
        self.w4.plot(self.w4_data3, pen="y")

        # self.w4_label = pg.LabelItem(justify='right')
        self.w4_label = pg.TextItem()
        self.w4.addItem(self.w4_label)

        self.vb = self.w4.plotItem.vb

        # cross hair
        self.w4_vLine = pg.InfiniteLine(angle=90, movable=False)
        self.w4_hLine = pg.InfiniteLine(angle=0, movable=False)
        self.w4.addItem(self.w4_vLine, ignoreBounds=True)
        self.w4.addItem(self.w4_hLine, ignoreBounds=True)

        self.proxy = pg.SignalProxy(self.w4.scene().sigMouseMoved, rateLimit=60, slot=self.mouseMoved)

        # self.w4.setAutoVisible(x=False, y=False)
        # self.w4.setMouseEnabled(x=False, y=False)
        # d4.addWidget(self.w4)

        # Dock5--数据显示面板
        self.w5 = pg.LayoutWidget()
        # 添加前置标签
        show_num_label = QLabel("数据量")
        show_min_label = QLabel("最小值")
        show_max_label = QLabel("最大值")
        show_range_label = QLabel("极差")
        show_avg_label = QLabel("平均值")
        show_mid_label = QLabel("中位数")
        show_var_label = QLabel("方差")
        show_std_label = QLabel("标准差")

        # 添加行编辑器
        self.show_num = QLineEdit()
        self.show_min = QLineEdit()
        self.show_max = QLineEdit()
        self.show_range = QLineEdit()
        self.show_avg = QLineEdit()
        self.show_mid = QLineEdit()
        self.show_var = QLineEdit()
        self.show_std = QLineEdit()
        # 文本框只读
        self.show_num.setReadOnly(True)
        self.show_min.setReadOnly(True)
        self.show_max.setReadOnly(True)
        self.show_range.setReadOnly(True)
        self.show_avg.setReadOnly(True)
        self.show_mid.setReadOnly(True)
        self.show_var.setReadOnly(True)
        self.show_std.setReadOnly(True)

        # self.show_min.setAlignment(Qt.AlignCenter)
        # 添加Label
        self.w5.addWidget(show_num_label, row=0, col=0)
        self.w5.addWidget(show_avg_label, row=0, col=2)
        self.w5.addWidget(show_mid_label, row=1, col=0)
        self.w5.addWidget(show_var_label, row=1, col=2)
        self.w5.addWidget(show_std_label, row=2, col=0)
        self.w5.addWidget(show_range_label, row=2, col=2)
        self.w5.addWidget(show_max_label, row=3, col=0)
        self.w5.addWidget(show_min_label, row=3, col=2)
        # 添加Text
        self.w5.addWidget(self.show_num, row=0, col=1)
        self.w5.addWidget(self.show_avg, row=0, col=3)
        self.w5.addWidget(self.show_mid, row=1, col=1)
        self.w5.addWidget(self.show_var, row=1, col=3)
        self.w5.addWidget(self.show_std, row=2, col=1)
        self.w5.addWidget(self.show_range, row=2, col=3)
        self.w5.addWidget(self.show_max, row=3, col=1)
        self.w5.addWidget(self.show_min, row=3, col=3)

        self.trans_data.connect(self.update_data)

        # 添加Qtable
        self.matrix_table = QTableWidget()
        self.matrix_table.setColumnCount(10)  # 设置表格一共有10列
        self.matrix_table.setRowCount(10)  # 设置表格一共有10列
        self.matrix_table.setStyleSheet(
            "QHeaderView::section{background-color:rgb(155, 194, 230);font:11pt '宋体';color: black;};")
        for i in range(0, 10):
            self.matrix_table.setColumnWidth(i, 60)
            self.matrix_table.setRowHeight(i, 60)
        self.matrix_table.setEditTriggers(QTableView.NoEditTriggers)

        self.w5.addWidget(self.matrix_table, row=4, col=0, colspan=4)
        self.trans_data.connect(self.update_matrix)
        d5.addWidget(self.w5)

        # Dock6--高级设置
        w6 = pg.LayoutWidget()
        w13 = pg.LayoutWidget()
        # 树形结构
        self.db_tree = QTreeWidget()
        # 设置列数
        self.db_tree.setColumnCount(2)
        # 设置树形控件头部的标题
        self.db_tree.setHeaderLabels(['选项', '状态'])

        self.db_root = QTreeWidgetItem(self.db_tree)
        self.db_root.setText(0, '数据库')
        # 设置树形控件的列的宽度
        self.db_tree.setColumnWidth(0, 160)
        # 设置子节点
        self.db_tree_real = QTreeWidgetItem(self.db_root)
        self.db_tree_real.setText(0, '实时录入数据库')
        self.db_tree_real.setCheckState(0, Qt.Unchecked)
        self.db_tree_timing = QTreeWidgetItem(self.db_root)
        self.db_tree_timing.setText(0, '定时录入数据库')
        self.db_tree_timing.setCheckState(0, Qt.Unchecked)
        self.db_tree_setTime = QTreeWidgetItem(self.db_tree_timing)
        self.db_tree_setTime.setText(0, '当前定时')
        self.db_tree_dataType = QTreeWidgetItem(self.db_tree_timing)
        self.db_tree_dataType.setText(0, '数据类型')
        self.db_tree_dataType.setCheckState(0, Qt.Checked)
        self.db_tree_time = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_time.setText(0, '时间')
        self.db_tree_time.setCheckState(0, Qt.Checked)
        self.db_tree_id = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_id.setText(0, '测试编号')
        self.db_tree_id.setCheckState(0, Qt.Checked)
        self.db_tree_weight = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_weight.setText(0, '砝码质量')
        self.db_tree_weight.setCheckState(0, Qt.Checked)
        self.db_tree_num = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_num.setText(0, '数据量')
        self.db_tree_num.setCheckState(0, Qt.Checked)
        self.db_tree_avg = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_avg.setText(0, '平均值')
        self.db_tree_avg.setCheckState(0, Qt.Checked)
        self.db_tree_mid = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_mid.setText(0, '中位数')
        self.db_tree_mid.setCheckState(0, Qt.Checked)
        self.db_tree_var = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_var.setText(0, '方差')
        self.db_tree_var.setCheckState(0, Qt.Checked)
        self.db_tree_std = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_std.setText(0, '标准差')
        self.db_tree_std.setCheckState(0, Qt.Checked)
        self.db_tree_range = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_range.setText(0, '极差')
        self.db_tree_range.setCheckState(0, Qt.Checked)
        self.db_tree_max = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_max.setText(0, '最大值')
        self.db_tree_max.setCheckState(0, Qt.Checked)
        self.db_tree_min = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_min.setText(0, '最小值')
        self.db_tree_min.setCheckState(0, Qt.Checked)
        self.db_tree_matrix = QTreeWidgetItem(self.db_tree_dataType)
        self.db_tree_matrix.setText(0, '矩阵数据')
        self.db_tree_matrix.setCheckState(0, Qt.Checked)
        self.db_tree.expandAll()

        id_label = QLabel('测试编号')
        self.id_data = QLineEdit()
        self.id_data.setPlaceholderText('请输入命名')

        timer_btn = QPushButton('打开定时器')
        timer_btn.setIcon(QIcon('timer.png'))
        timer_btn.clicked.connect(self.open_timer)
        database_btn = QPushButton('打开数据库')
        database_btn.setIcon(QIcon('database.png'))

        # 倒计时记录
        countdown_label = QLabel('倒计时')
        percent_label = QLabel('变化量')
        count_id_label = QLabel('编号')
        self.countdown_data = QDoubleSpinBox()
        self.percent_data = QDoubleSpinBox()
        self.count_id = QLineEdit()
        self.countdown_btn = QPushButton('开始倒计时')
        self.countdown_btn.clicked.connect(self.update_countdown)

        self.countdown_data.setRange(0, 999.99)
        self.percent_data.setRange(0, 100)
        self.countdown_data.setSuffix('s')
        self.percent_data.setSuffix('%')

        w13.addWidget(countdown_label, row=0, col=0)
        w13.addWidget(self.countdown_data, row=0, col=1)
        w13.addWidget(count_id_label, row=0, col=2)
        w13.addWidget(self.count_id, row=0, col=3)
        w13.addWidget(percent_label, row=1, col=0)
        w13.addWidget(self.percent_data, row=1, col=1)
        w13.addWidget(self.countdown_btn, row=1, col=2, colspan=2)

        w6.addWidget(self.db_tree, row=0, col=0, colspan=2)
        w6.addWidget(id_label, row=1, col=0)
        w6.addWidget(self.id_data, row=1, col=1)
        w6.addWidget(timer_btn, row=2, col=0)
        w6.addWidget(database_btn, row=2, col=1)
        d6.addWidget(w6)
        d6.addWidget(w13)

        # Dock7--控制面板
        # 隐藏标题栏，无法拖动
        d7.hideTitleBar()
        w7 = pg.LayoutWidget()
        w9 = pg.LayoutWidget()
        # 标签title
        protocol_label = QLabel('通信协议')
        port_label = QLabel('串口选择')
        bps_label = QLabel('波特率')
        voltage_label = QLabel('输入电压(V)')
        resistance_label = QLabel('分压电阻(Ω)')
        internal_label = QLabel('内阻(Ω)')
        weight_label = QLabel('砝码质量(g)')

        w7.addWidget(protocol_label, row=0, col=0)
        w7.addWidget(port_label, row=1, col=0)
        w7.addWidget(bps_label, row=2, col=0)
        w7.addWidget(voltage_label, row=3, col=0)
        w7.addWidget(resistance_label, row=4, col=0)
        w7.addWidget(internal_label, row=5, col=0)
        w7.addWidget(weight_label, row=6, col=0)

        # 按钮
        self.start_btn = QPushButton('打开串口')
        self.stop_btn = QPushButton('暂停')
        self.screenshot_btn = QPushButton('一键截图')
        self.calibrate_btn = QPushButton('校准')
        self.record_btn = QPushButton('写入数据库')
        self.record_btn.setEnabled(True)
        self.refresh_btn = QPushButton('清空数据')

        self.calibrate_btn.setToolTip('以当前数值为基准，重新标定')
        self.screenshot_btn.setToolTip('截图当前窗口，并保存至本地文件夹')
        self.record_btn.setToolTip('请前往高级设置')

        self.stop_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.startThread)
        self.stop_btn.clicked.connect(self.stop_resume)
        self.screenshot_btn.clicked.connect(self.screen_shot)
        self.calibrate_btn.clicked.connect(self.re_calibrate)
        self.record_btn.clicked.connect(self.start_database)
        self.refresh_btn.clicked.connect(self.clear_GUI)
        w9.addWidget(self.start_btn, row=0, col=0, colspan=2)
        w9.addWidget(self.stop_btn, row=1, col=0, colspan=2)
        w9.addWidget(self.refresh_btn, row=2, col=0, colspan=2)
        w9.addWidget(self.calibrate_btn, row=3, col=1)
        w9.addWidget(self.record_btn, row=4, col=0, colspan=2)
        w9.addWidget(self.screenshot_btn, row=5, col=0, colspan=2)

        # 单行文本框
        self.internal_data = QLineEdit()
        self.internal_data.setPlaceholderText('请输入数字')
        self.weight_data = QLineEdit()
        self.weight_data.setPlaceholderText('请输入数字')
        # 校验是否为数字
        validator_weight = QDoubleValidator(0, 10000, 2)
        validator_weight.setNotation(QDoubleValidator.StandardNotation)
        self.internal_data.setValidator(validator_weight)
        self.weight_data.setValidator(validator_weight)
        w7.addWidget(self.internal_data, row=5, col=1)
        w7.addWidget(self.weight_data, row=6, col=1)

        # 复选框
        self.calibrate_checkbox = QCheckBox()
        w9.addWidget(self.calibrate_checkbox, row=3, col=0)
        self.calibrate_checkbox.stateChanged.connect(self.calibrate_check)
        # 下拉框
        self.protocol_combobox = QComboBox()
        self.port_combobox = CustomComboBox()
        self.bps_combobox = QComboBox()
        self.voltage_combobox = QComboBox()
        self.resistance_combobox = QComboBox()
        self.bps_combobox.setEditable(True)
        self.resistance_combobox.setEditable(True)
        self.protocol_combobox.addItems(['测试治具', '扫地机'])
        self.port_combobox.addItems(self.usable_port)
        self.bps_combobox.addItems(['115200', '230400'])
        self.voltage_combobox.addItems(['3.3', '5'])
        self.resistance_combobox.addItems(['200', '2000', '20000'])
        self.protocol_combobox.setCurrentIndex(0)
        self.port_combobox.setCurrentIndex(0)
        self.bps_combobox.setCurrentIndex(0)
        self.voltage_combobox.setCurrentIndex(0)
        self.resistance_combobox.setCurrentIndex(0)
        self.protocol_combobox.currentIndexChanged[int].connect(self.update_protocol)  # 条目发生改变，发射信号，传递条目内容

        w7.addWidget(self.protocol_combobox, row=0, col=1)
        w7.addWidget(self.port_combobox, row=1, col=1)
        w7.addWidget(self.bps_combobox, row=2, col=1)
        w7.addWidget(self.voltage_combobox, row=3, col=1)
        w7.addWidget(self.resistance_combobox, row=4, col=1)


        w12 = pg.LayoutWidget()
        row_label = QLabel('行数')
        col_label = QLabel('列数')
        # row_label.setAlignment(Qt.AlignCenter)
        # col_label.setAlignment(Qt.AlignCenter)
        w12.addWidget(row_label, row=0, col=0)
        w12.addWidget(col_label, row=1, col=0)

        # 微调框
        self.row_data = QSpinBox()
        self.col_data = QSpinBox()
        self.row_data.setRange(1, 1000)
        self.col_data.setRange(1, 1000)
        self.row_data.valueChanged.connect(self.update_row)
        self.col_data.valueChanged.connect(self.update_col)
        w12.addWidget(self.row_data, row=0, col=1)
        w12.addWidget(self.col_data, row=1, col=1)

        # 添加TextBrowser
        w10 = pg.LayoutWidget()
        self.sys_browser = QPlainTextEdit()
        self.sys_browser.setReadOnly(True)
        w10.addWidget(self.sys_browser)

        w11 = pg.LayoutWidget()
        # type_label = QLabel('数据类型：')
        voltage_radio = QRadioButton('电压值')
        resistance_radio = QRadioButton('电阻值')
        weight_radio = QRadioButton('重量值')
        pressure_radio = QRadioButton('压力值')
        # w11.addWidget(type_label, row=0, col=0)
        w11.addWidget(voltage_radio, row=0, col=0)
        w11.addWidget(resistance_radio, row=0, col=1)
        w11.addWidget(weight_radio, row=1, col=0)
        w11.addWidget(pressure_radio, row=1, col=1)
        voltage_radio.setChecked(True)
        self.type_group = QButtonGroup()
        self.type_group.addButton(voltage_radio, 0)
        self.type_group.addButton(resistance_radio, 1)
        self.type_group.addButton(weight_radio, 2)
        self.type_group.addButton(pressure_radio, 3)
        self.type_group.buttonClicked[int].connect(self.type_check)

        d7.addWidget(w10, row=0, col=0, colspan=3)
        d7.addWidget(w12, row=1, col=0)
        d7.addWidget(w11, row=1, col=1, colspan=2)
        d7.addWidget(w7, row=2, col=0, colspan=2)
        d7.addWidget(w9, row=2, col=2)

        # 数据库
        self.real_table_name = ''
        self.timer_table_name = ''
        self.id_database = 0
        self.current_id = ''
        self.current_timer = 0
        self.current_last = 0
        self.timer_exe_0 = QTimer()
        self.timer_exe_1 = QTimer()
        self.timer_exe_2 = QTimer()
        self.timer_exe_3 = QTimer()
        self.timer_exe_4 = QTimer()
        self.timer_stop_signal = 0
        self.countdown_signal = True
        self.percent_num = 0
        self.count_save = 0
        self.count_start_time = ''
        self.count_table_name = ''

        self.copy_data = {'save_list': [], 'num_data': 0, 'min_data': 0,
                          'max_data': 0, 'range_data': 0, 'avg_data': 0,
                          'mid_data': 0, 'var_data': 0, 'std_data': 0,
                          'matrix_list': [[]], 'time_data': 0, 'hour_data': ''}
        self.trans_data.connect(self.copy_signal)

        # 子窗口
        self.child_timer = ChildTimer()
        self.child_timer.trans_check.connect(self.database_check)

    def print_com(self):  # 打印可用串口
        port_list = list(serial.tools.list_ports.comports())
        # if len(port_list) == 0:
        #     self.usable_port = ['找不到串口']
        for i in range(0, len(port_list)):
            port = str(port_list[i])
            index = port.find('-')
            self.usable_port.append(port[:index-1])

    def update_protocol(self):
        if self.protocol_combobox.currentIndex() == 0:
            self.protocol_head = "a55a01"
            self.head_len = 6
        elif self.protocol_combobox.currentIndex() == 1:
            self.protocol_head = "a55a55aa01"
            self.head_len = 8

    # def update_internal(self):
    #     self.internal_resistance = self.internal_data.value()

    def update_row(self):
        self.row_num = self.row_data.value()

    def update_col(self):
        self.col_num = self.col_data.value()

    def type_check(self):
        if self.type_group.checkedId() == 0:
            self.data_type = 0
        elif self.type_group.checkedId() == 1:
            self.data_type = 1
        elif self.type_group.checkedId() == 2:
            self.data_type = 2
        else:
            self.data_type = 3


    def startThread(self):   # 打开各线程
        try:
            self.printf("开始连接串口...")
            self.loop = True
            self.port = self.port_combobox.currentText()
            self.baud = int(self.bps_combobox.currentText())
            self.voltage_num = float(self.voltage_combobox.currentText())
            self.resistance_num = int(self.resistance_combobox.currentText())
            try:
                self.internal_resistance = float(self.internal_data.text())
            except:
                self.internal_resistance = 0
            # 结合波特率和传输的数据量计算出数据发送所需的时间，计算timeout。
            serial_port = serial.Serial(self.port, self.baud, timeout=0.1)
            read_thread = threading.Thread(target=self.receive_data, args=(serial_port,))
            check_thread = threading.Thread(target=self.check_sum)
            calculate_thread = threading.Thread(target=self.calculate_data)
            read_thread.setDaemon(True)  # 守护线程
            check_thread.setDaemon(True)
            calculate_thread.setDaemon(True)
            read_thread.start()  # 启动线程
            check_thread.start()
            calculate_thread.start()
        except Exception as e:
            self.loop = False
            self.printf("串口连接失败：" + str(e))
            self.start_btn.setText('打开串口')
            self.id_data.setReadOnly(False)
            self.weight_data.setReadOnly(False)
            self.row_data.setReadOnly(False)
            self.col_data.setReadOnly(False)
        else:
            self.printf("串口连接成功！")
            self.start_btn.setText('关闭串口')
            self.stop_btn.setEnabled(True)
            self.id_data.setReadOnly(True)
            self.weight_data.setReadOnly(True)
            self.row_data.setReadOnly(True)
            self.col_data.setReadOnly(True)
            # self.internal_data.setReadOnly(True)
            self.id_data.setPlaceholderText('请先暂停')
            self.weight_data.setPlaceholderText('请先暂停')
            # self.internal_data.setPlaceholderText('请先暂停')

    def receive_data(self, port):
        # 循环接收数据，此为死循环
        self.printf("开始接收数据...")
        serial_list = [{"data": "", "sec_time": 0, "hour_time": ""} for i in range(2)]
        while self.loop:
            try:
                if port.in_waiting:
                    # 整体接收
                    data = port.read_all().hex()  # 接受所有数据并转成16进制
                    # print(data)
                    sec_time = perf_counter()
                    hour_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    index = data.find(self.protocol_head)  # 找到包头
                    # print(index)
                    if index == -1:  # 如果没有包头，补给list中的最后一组
                        serial_list[-1]["data"] = serial_list[-1]["data"] + data

                    else:  # 如果有包头，包头前的字符补给最后一组，然后把最后一组前移一位，包头后的字符占据list最后一位
                        serial_list[-1]["data"] = serial_list[-1]["data"] + data[:index]
                        serial_list.pop(0)
                        serial_list.append({"data": data[index:], "sec_time": sec_time, "hour_time": hour_time})

                    # print(serial_list)
                    self.receive_list = deepcopy(serial_list)
            except Exception as e:
                print("接收环节出错：", e)
                time.sleep(0.005)

    def check_sum(self):
        while self.loop:
            try:
                save_receive_list = deepcopy(self.receive_list[0])

                double_list = [save_receive_list["data"][i:i + 2] for i in
                               range(0, len(save_receive_list["data"]), 2)]  # 按字节分隔成数组
                decimal_list = [int(i, 16) for i in double_list[:-2]]  # 16进制转10进制
                check_data = int(double_list[-1] + double_list[-2], 16)  # 校验和
                sum_data = sum(decimal_list) % 65536
                if sum_data == check_data:  # 除开校验位，自身加和
                    matrix_data = double_list[self.head_len:-2]
                    reform_data = [matrix_data[i+1] + matrix_data[i] for i in
                                   range(0, len(matrix_data), 2)]
                    divide_data = np.array([int(i, 16) for i in reform_data]) / 1000
                    self.data_list = deepcopy({"data": divide_data, "sec_time": save_receive_list["sec_time"],
                                               "hour_time": save_receive_list["hour_time"]})
                    time.sleep(0.01)
                else:
                    print("校验出错")
            except Exception as e:
                print("串口数据校验环节出错：", e)
                time.sleep(0.005)

    def calculate_data(self):
        while self.loop:
            try:
                copy_data = deepcopy(self.data_list)

                if self.calibrate_signal:
                    save_list = copy_data["data"] - self.calibrate_copy
                else:
                    save_list = copy_data["data"]

                if self.data_type == 0:   #显示电压值
                    save_list = np.around(np.array(save_list), 3)
                elif self.data_type == 1:    #显示电阻值
                    # save_list = ((self.voltage_num - np.array(save_list)) * self.resistance_num) / self.voltage_num
                    # save_list = (np.array(save_list) * self.resistance_num) / (self.voltage_num - np.array(save_list))
                    # save_list = ((self.voltage_num - np.array(save_list)) * self.resistance_num) / np.array(save_list)
                    save_list = np.maximum(save_list, 0.001)
                    save_list = np.divide(np.multiply(np.subtract(self.voltage_num, save_list), self.resistance_num), save_list)
                    save_list = np.around(save_list, 1)
                    save_list = save_list - self.internal_resistance

                list_len = len(save_list)
                matrix_len = self.row_num * self.col_num
                if list_len == matrix_len:
                    save_list = np.array(save_list)
                    self.matrix_list = save_list.reshape((self.row_num, self.col_num))
                elif list_len > matrix_len:
                    less_num = matrix_len - list_len
                    save_list = np.array(save_list[:less_num])
                    self.matrix_list = save_list.reshape((self.row_num, self.col_num))
                else:
                    more_num = matrix_len - list_len
                    reform_list = deepcopy(save_list)
                    reform_list = np.append(reform_list, np.zeros(more_num))
                    self.matrix_list = reform_list.reshape((self.row_num, self.col_num))

                self.num_data = len(save_list)
                self.min_data = min(save_list)
                self.max_data = max(save_list)
                self.range_data = round(self.max_data - self.min_data, 3)
                self.avg_data = round(float(np.mean(save_list)), 3)
                self.mid_data = round(float(np.median(save_list)), 3)
                self.var_data = round(float(np.var(save_list)), 3)
                self.std_data = round(float(np.std(save_list, ddof=0)), 3)

                if self.stop_signal == 0:

                    signal = {'save_list': save_list, 'num_data': self.num_data, 'min_data': self.min_data,
                              'max_data': self.max_data, 'range_data': self.range_data, 'avg_data': self.avg_data,
                              'mid_data': self.mid_data, 'var_data': self.var_data, 'std_data': self.std_data,
                              'matrix_list': self.matrix_list, 'time_data': copy_data["sec_time"],
                              'hour_data': copy_data["hour_time"]}

                    self.trans_data.emit(signal)

                time.sleep(0.02)

            except Exception as e:
                print("串口数据分析环节出错:", e)
                time.sleep(0.005)

    def update_map(self, signal):
        self.img.setImage(signal['matrix_list'], autoLevels=self.auto_map, levels=self.map_level)

    def mapColor_check(self):
        if self.d1_group.checkedId() == 0:
            gray_map = pg.colormap.get(name='gray', source='matplotlib')
            self.bar = pg.ColorBarItem(interactive=False, colorMap=gray_map)
            self.bar.setImageItem(self.img)
        else:
            jet_map = pg.colormap.get(name='jet', source='matplotlib')
            self.bar = pg.ColorBarItem(interactive=False, colorMap=jet_map)
            self.bar.setImageItem(self.img)

    def automap_check(self):
        if self.auto_map:
            self.auto_map = False
        else:
            self.auto_map = True

    def update_mapLevel(self):
        self.map_level = (self.min_map.value(), self.max_map.value())

    def update_time(self, signal):
        if len(self.w2_data) <= 100:
            self.w2_data.append(signal['avg_data'])
        else:
            self.w2_data[:-1] = self.w2_data[1:]
            self.w2_data[-1] = signal['avg_data']
        if self.w2_time == -1:
            self.w2_time = signal['time_data']
        else:
            self.w2_xPos = signal['time_data'] - self.w2_time

        self.w2_curve.setData(self.w2_data)
        self.w2_curve.setPos(self.w2_xPos, 0)

    def update_wholeTime(self, signal):
        if len(self.w8_data) > 10000:
            self.w8_data.pop(0)
        self.w8_data.append(signal['avg_data'])

        if self.w8_time == -1:
            self.w8_time = signal['time_data']
        elif len(self.w8_timeList) <= 10000:
            self.w8_timeList.append(signal['time_data'] - self.w8_time)
        else:
            self.w8_timeList.pop(0)
            self.w8_timeList.append(signal['time_data'] - self.w8_time)

        self.w8_curve.setData(x=self.w8_timeList, y=self.w8_data)

    def update_histogram(self, signal):
        interval_list = (1.1 * signal['mid_data'], 0.9 * signal['mid_data'])
        interval_max = max(interval_list)
        interval_min = min(interval_list)
        interval = interval_max - interval_min

        if interval == 0:
            interval = 1

        num_right = math.ceil((signal['max_data'] - interval_max) / interval)
        num_left = math.ceil((interval_min - signal['min_data']) / interval)
        num_interval = num_left + num_right + 1

        if num_interval <= 5:
            num_interval = 5
            range_max = 2 * interval + interval_max
            range_min = interval_min - (2 * interval)
        else:
            range_max = num_right * interval + interval_max
            range_min = interval_min - (num_left * interval)

        y, x = np.histogram(signal['save_list'], bins=num_interval, range=(range_min, range_max), density=self.histogram_density)
        self.w3.plot(x, y, stepMode="center", fillLevel=0, fillOutline=True, brush='#00aaff', clear=True)

    def update_weight(self):
        pass

    def fitting(self, x, a, b):
        return b + a / x

    def mouseMoved(self, evt):
        pos = evt[0]  ## using signal proxy turns original arguments into a tuple
        if self.w4.sceneBoundingRect().contains(pos):
            mousePoint = self.vb.mapSceneToView(pos)
            index = int(mousePoint.x())
            try:
                if -1 <= index <= len(self.w4_data1):
                    self.w4_label.setHtml(
                        "<p style='color:white'><strong>x：{0}</strong></p><p style='color:red'>y1：{1}</p><p style='color:green'>y2：{2}</p><p style='color:yellow'>y3：<span style='color:yellow;'>{3}</span></p>".format(
                            mousePoint.x(), self.w4_data1[index], self.w4_data2[index], self.w4_data3[index]))
                    self.w4_label.setPos(mousePoint.x(), mousePoint.y())  # 设置label的位置
                self.w4_vLine.setPos(mousePoint.x())
                self.w4_hLine.setPos(mousePoint.y())
            except:
                pass

    def histogram_check(self):
        if self.d3_group.checkedId() == 0:
            self.histogram_density = False
        else:
            self.histogram_density = True

    def update_data(self, signal):
        self.show_num.setText(str(signal['num_data']))
        self.show_min.setText(str(signal['min_data']))
        self.show_max.setText(str(signal['max_data']))
        self.show_range.setText(str(signal['range_data']))
        self.show_avg.setText(str(signal['avg_data']))
        self.show_mid.setText(str(signal['mid_data']))
        self.show_var.setText(str(signal['var_data']))
        self.show_std.setText(str(signal['std_data']))

    def update_matrix(self, signal):
        row = len(signal['matrix_list'])
        col = len(signal['matrix_list'][0])
        if row > 10:
            row = 10
        if col > 10:
            col = 10
        for r in range(0, row):
            for c in range(0, col):
                self.matrix_table.setItem(r, c, QTableWidgetItem(str(signal['matrix_list'][-r-1][c])))

    def update_history(self, signal):
        self.show_history.appendPlainText(str(signal))

    def clear_GUI(self):
        # 总览图数据list清空
        self.w8_data = []
        self.w8_timeList = [0]
        self.w8_time = -1
        # 时间变化图list清空
        self.w2_data = []
        self.w2_time = -1
        self.w2_xPos = 0

        self.img.clear()
        self.w2_curve.clear()
        self.w3.clear()
        self.w4.clear()
        self.w8_curve.clear()

        self.show_num.clear()
        self.show_min.clear()
        self.show_max.clear()
        self.show_range.clear()
        self.show_avg.clear()
        self.show_mid.clear()
        self.show_var.clear()
        self.show_std.clear()
        self.matrix_table.clearContents()

        self.printf("已清空界面")

    def stop_resume(self):
        if self.stop_signal == 0:
            self.stop_signal = 1
            self.stop_btn.setText('恢复')
            self.id_data.setReadOnly(False)
            self.weight_data.setReadOnly(False)
            self.row_data.setReadOnly(False)
            self.col_data.setReadOnly(False)
            self.id_data.setPlaceholderText('请输入命名')
            self.weight_data.setPlaceholderText('请输入数字')
            self.printf("已暂停绘制和记录")
        else:
            self.stop_signal = 0
            self.stop_btn.setText('暂停')
            self.id_data.setReadOnly(True)
            self.weight_data.setReadOnly(True)
            self.row_data.setReadOnly(True)
            self.col_data.setReadOnly(True)
            self.id_data.setPlaceholderText('先暂停后输入')
            self.weight_data.setPlaceholderText('先暂停后输入')
            self.matrix_table.clearContents()
            self.printf("已恢复绘制和记录")

    def to_db_btn(self):
        self.record_btn.setText('写入数据库')
        self.timer_stop_signal = 0
        self.conn.commit()

    def database_check(self):
        self.db_tree_timing.setCheckState(0, Qt.Checked)

    def start_database(self):
        if self.timer_stop_signal == 0:
            self.timer_stop_signal = 1
            self.record_btn.setText('停止写入')
            try:
                self.conn = sqlite3.connect('History_Data.db')
                self.c = self.conn.cursor()
                self.printf("数据库连接成功")
                if self.db_tree_real.checkState(0) == Qt.Checked and self.db_tree_timing.checkState(0) == Qt.Checked:
                    msgBox = QMessageBox()
                    msgBox.setWindowTitle('注意')
                    msgBox.setIcon(QMessageBox.Warning)
                    msgBox.setText('只能选择一种录入方式')
                    real_save = msgBox.addButton('实时录入', QMessageBox.AcceptRole)
                    msgBox.addButton('定时录入', QMessageBox.RejectRole)
                    msgBox.addButton('取消', QMessageBox.DestructiveRole)
                    msgBox.setDefaultButton(real_save)  # 设置了默认的按钮是保存
                    reply = msgBox.exec()
                    if reply == QMessageBox.AcceptRole:
                        self.db_tree_timing.setCheckState(0, Qt.Unchecked)
                        self.timer_stop_signal = 0
                        self.start_database()
                    elif reply == QMessageBox.RejectRole:
                        self.db_tree_real.setCheckState(0, Qt.Unchecked)
                        self.timer_stop_signal = 0
                        self.start_database()
                    else:
                        self.db_tree_real.setCheckState(0, Qt.Unchecked)
                        self.db_tree_timing.setCheckState(0, Qt.Unchecked)
                        self.printf('数据库已断开连接，请在高级设置中勾选写入方式')
                        self.to_db_btn()

                elif self.db_tree_real.checkState(0) == Qt.Checked:
                    try:
                        self.real_table_name = datetime.datetime.now().strftime("Real_%Y_%m_%d")
                        real_table_unit = '''(序号 INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                                               时间     TEXT,
                                               测试编号  TEXT,
                                               砝码质量  TEXT,
                                               数据量    INT,
                                               平均值    REAL,
                                               中位数    REAL,
                                               方差     REAL,
                                               标准差    REAL,
                                               极差     REAL,
                                               最大值    REAL,
                                               最小值    REAL,
                                               矩阵数据   TEXT)'''
                        self.c.execute("CREATE TABLE " + self.real_table_name + real_table_unit)
                        self.printf("实时数据表创建成功")
                    except sqlite3.OperationalError as e:
                        self.printf(str(e) + ", 开始写入")
                    finally:
                        self.conn.commit()
                        self.trans_data.connect(self.real_insert)

                elif self.db_tree_timing.checkState(0) == Qt.Checked:
                    try:
                        self.timer_table_name = datetime.datetime.now().strftime("Timer_%Y_%m_%d")
                        timer_table_unit = '''(序号 INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                                               时间     TEXT,
                                               测试编号  TEXT,
                                               砝码质量  TEXT,
                                               数据量    INT,
                                               平均值    REAL,
                                               中位数    REAL,
                                               方差     REAL,
                                               标准差    REAL,
                                               极差     REAL,
                                               最大值    REAL,
                                               最小值    REAL,
                                               矩阵数据   TEXT)'''
                        self.c.execute("CREATE TABLE " + self.timer_table_name + timer_table_unit)
                        self.printf("定时数据表创建成功")
                    except sqlite3.OperationalError as e:
                        self.printf(str(e) + ", 开始写入")
                    finally:
                        self.conn.commit()
                        self.manage_timer_0()
                        QTimer.singleShot(self.child_timer.record_info['last'][0] * 60000, self.manage_timer_1)
                        QTimer.singleShot(sum(self.child_timer.record_info['last'][:2]) * 60000, self.manage_timer_2)
                        QTimer.singleShot(sum(self.child_timer.record_info['last'][:3]) * 60000, self.manage_timer_3)
                        QTimer.singleShot(sum(self.child_timer.record_info['last'][:4]) * 60000, self.manage_timer_4)
                        QTimer.singleShot(sum(self.child_timer.record_info['last'][:5]) * 60000, self.manage_timer_stop)

                else:
                    self.printf('数据库已断开连接，请在高级设置中勾选写入方式')
                    self.to_db_btn()

            except Exception as e:
                self.printf("创建/连接数据库失败：" + str(e))

        else:
            try:
                self.trans_data.disconnect(self.real_insert)
                self.printf('已停止实时写入数据库')
            except TypeError:
                self.timer_exe_0.stop()
                self.timer_exe_1.stop()
                self.timer_exe_2.stop()
                self.timer_exe_3.stop()
                self.timer_exe_4.stop()
                self.printf('已停止定时写入数据库')
            finally:
                self.to_db_btn()

    def real_insert(self, signal):
        try:
            table_col = '''(时间, 测试编号, 砝码质量, 数据量, 平均值, 中位数, 方差, 标准差, 极差, 最大值, 最小值, 矩阵数据)'''
            sql = "INSERT INTO " + self.real_table_name + table_col + "values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            name_database = self.id_data.text()
            weight_database = self.weight_data.text()
            datas = (signal['hour_data'], name_database, weight_database, signal["num_data"],
                     signal['avg_data'], signal['mid_data'], signal['var_data'], signal['std_data'],
                     signal['range_data'], signal['max_data'], signal['min_data'], str(signal['matrix_list']))
            self.c.execute(sql, datas)
            self.conn.commit()
        except Exception as e:
            self.printf("上传到数据库失败：" + str(e))

    def manage_timer_0(self):
        if self.child_timer.record_info['timer'][0] > 0:
            self.current_id = self.child_timer.record_info['id'][0]
            self.timer_exe_0.timeout.connect(self.timer_insert)
            self.timer_exe_0.start(self.child_timer.record_info['timer'][0] * 1000)
            self.printf('第一组定时器' + self.current_id + '开始记录... 记录频率：'
                        + str(round(self.child_timer.record_info['timer'][0], 2)) + '秒/次；持续时长：'
                        + str(self.child_timer.record_info['last'][0]) + '分钟')
        elif self.child_timer.record_info['last'][0] > 0:
            self.printf('第一组定时器' + self.child_timer.record_info['id'][0] + '已打开... 暂停记录'
                        + str(self.child_timer.record_info['last'][0]) + '分钟')

    def manage_timer_1(self):
        self.timer_exe_0.stop()
        if self.child_timer.record_info['timer'][1] > 0:
            self.current_id = self.child_timer.record_info['id'][1]
            self.timer_exe_1.timeout.connect(self.timer_insert)
            self.timer_exe_1.start(self.child_timer.record_info['timer'][1] * 1000)
            self.printf('第二组定时器' + self.current_id + '开始记录... 记录频率：'
                        + str(round(self.child_timer.record_info['timer'][1], 2)) + '秒/次；持续时长：'
                        + str(self.child_timer.record_info['last'][1]) + '分钟')
        elif self.child_timer.record_info['last'][1] > 0:
            self.printf('第二组定时器' + self.child_timer.record_info['id'][1] + '已打开... 暂停记录'
                        + str(self.child_timer.record_info['last'][1]) + '分钟')

    def manage_timer_2(self):
        self.timer_exe_1.stop()
        if self.child_timer.record_info['timer'][2] > 0:
            self.current_id = self.child_timer.record_info['id'][2]
            self.timer_exe_2.timeout.connect(self.timer_insert)
            self.timer_exe_2.start(self.child_timer.record_info['timer'][2] * 1000)
            self.printf('第三组定时器' + self.current_id + '开始记录... 记录频率：'
                        + str(round(self.child_timer.record_info['timer'][2], 2)) + '秒/次；持续时长：'
                        + str(self.child_timer.record_info['last'][2]) + '分钟')
        elif self.child_timer.record_info['last'][2] > 0:
            self.printf('第三组定时器' + self.child_timer.record_info['id'][2] + '已打开... 暂停记录'
                        + str(self.child_timer.record_info['last'][2]) + '分钟')

    def manage_timer_3(self):
        self.timer_exe_2.stop()
        if self.child_timer.record_info['timer'][3] > 0:
            self.current_id = self.child_timer.record_info['id'][3]
            self.timer_exe_3.timeout.connect(self.timer_insert)
            self.timer_exe_3.start(self.child_timer.record_info['timer'][3] * 1000)
            self.printf('第四组定时器' + self.current_id + '开始记录... 记录频率：'
                        + str(round(self.child_timer.record_info['timer'][3], 2)) + '秒/次；持续时长：'
                        + str(self.child_timer.record_info['last'][3]) + '分钟')
        elif self.child_timer.record_info['last'][3] > 0:
            self.printf('第四组定时器' + self.child_timer.record_info['id'][3] + '已打开... 暂停记录'
                        + str(self.child_timer.record_info['last'][3]) + '分钟')

    def manage_timer_4(self):
        self.timer_exe_3.stop()
        if self.child_timer.record_info['timer'][4] > 0:
            self.current_id = self.child_timer.record_info['id'][4]
            self.timer_exe_4.timeout.connect(self.timer_insert)
            self.timer_exe_4.start(self.child_timer.record_info['timer'][4] * 1000)
            self.printf('第五组定时器' + self.current_id + '开始记录... 记录频率：'
                        + str(round(self.child_timer.record_info['timer'][4], 2)) + '秒/次；持续时长：'
                        + str(self.child_timer.record_info['last'][4]) + '分钟')
        elif self.child_timer.record_info['last'][4] > 0:
            self.printf('第五组定时器' + self.child_timer.record_info['id'][4] + '已打开... 暂停记录'
                        + str(self.child_timer.record_info['last'][4]) + '分钟')

    def manage_timer_stop(self):
        self.timer_exe_4.stop()
        self.printf('定时记录已完成，总耗时：' + str(sum(self.child_timer.record_info['last'])) + '分钟')
        self.to_db_btn()

    def timer_insert(self):
        try:
            table_col = '''(时间, 测试编号, 砝码质量, 数据量, 平均值, 中位数, 方差, 标准差, 极差, 最大值, 最小值, 矩阵数据)'''
            sql = "INSERT INTO " + self.timer_table_name + table_col + "values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            time_database = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-4]
            name_database = self.current_id
            weight_database = self.weight_data.text()
            datas = (time_database, name_database, weight_database, self.copy_data["num_data"],
                     self.copy_data['avg_data'], self.copy_data['mid_data'], self.copy_data['var_data'], self.copy_data['std_data'],
                     self.copy_data['range_data'], self.copy_data['max_data'], self.copy_data['min_data'], str(self.copy_data['matrix_list']))
            self.c.execute(sql, datas)
            self.conn.commit()
        except Exception as e:
            self.printf("上传到数据库失败：" + str(e))

    def update_countdown(self):
        if self.countdown_signal:
            self.percent_num = (100 - self.percent_data.value()) * 0.01 * self.copy_data['avg_data']
            # 数据库
            self.count_conn = sqlite3.connect('Countdown_Data.db')
            self.count_c = self.count_conn.cursor()
            try:
                self.count_table_name = datetime.datetime.now().strftime("Count_%Y_%m_%d")
                table_unit = '''(序号 INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                                               时间     TEXT,
                                               编号     TEXT,
                                               砝码质量  TEXT,
                                               倒计时    REAL,
                                               变化量    REAL,
                                               压感数据    REAL)'''
                self.count_c.execute("CREATE TABLE " + self.count_table_name + table_unit)
            except:
                pass
            # 连接槽函数
            self.count_conn.commit()
            self.trans_data.connect(self.count_compare)
            self.countdown_signal = False
            self.countdown_data.setReadOnly(True)
            self.percent_data.setReadOnly(True)
            self.count_id.setReadOnly(True)
            self.countdown_btn.setText('停止倒计时')
        else:
            self.trans_data.disconnect(self.count_compare)
            self.countdown_signal = True
            self.countdown_data.setReadOnly(False)
            self.percent_data.setReadOnly(False)
            self.count_id.setReadOnly(False)
            self.countdown_btn.setText('开始倒计时')
            self.count_conn.close()

    def count_compare(self, signal):
        if signal['avg_data'] < self.percent_num:
            self.count_start_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-5]
            QTimer.singleShot(self.countdown_data.value() * 1000, self.count_insert)
            self.printf('开始倒计时...')
            self.trans_data.disconnect(self.count_compare)

    def count_insert(self):
        try:
            table_col = '''(时间, 编号, 砝码质量, 倒计时, 变化量, 压感数据)'''
            sql = "INSERT INTO " + self.count_table_name + table_col + "values(?, ?, ?, ?, ?, ?)"
            datas = (self.count_start_time, self.count_id.text(), self.weight_data.text(), self.countdown_data.value(),
                     self.percent_data.value(), self.copy_data['avg_data'])
            self.count_c.execute(sql, datas)
            self.count_conn.commit()
            self.printf("倒计时已完成")
        except Exception as e:
            print(e)
            self.printf("倒计时写入数据库失败：" + str(e))
        finally:
            self.countdown_signal = True
            self.countdown_data.setReadOnly(False)
            self.percent_data.setReadOnly(False)
            self.count_id.setReadOnly(False)
            self.countdown_btn.setText('开始倒计时')
            self.count_conn.close()

    # 界面关闭时关闭数据库连接
    def closeEvent(self, event):
        self.conn.close()

    def screen_shot(self):
        try:
            name = datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            hwnd = FindWindow(None, "墨现科技--客户端1.1.2")
            ShowWindow(hwnd, SW_RESTORE)  # 强行显示界面，窗口最小化时无法截图
            screen = QApplication.primaryScreen()
            img = screen.grabWindow(hwnd).toImage()
            img.save('截图\\'+name + '.jpg')
            self.printf("截图已保存")
        except Exception as e:
            self.printf("截图保存失败：" + str(e))

    def re_calibrate(self):
        self.calibrate_copy = deepcopy(self.data_list["data"])
        self.printf('已标定当前数值为基准值')

    def calibrate_check(self):
        if self.calibrate_checkbox.isChecked():
            self.calibrate_signal = True
            self.calibrate_btn.setEnabled(True)
            self.printf("已打开手动校准")
        else:
            self.calibrate_signal = False
            self.calibrate_btn.setEnabled(False)
            self.printf("已恢复基准值为‘0’")

    def printf(self, text):
        time_print = datetime.datetime.now().strftime("%H:%M:%S ")
        self.sys_browser.appendPlainText(time_print + text)

    def copy_signal(self, signal):
        self.copy_data = signal

    def open_timer(self):
        self.child_timer.show()

class ChildTimer(QWidget):
    trans_check = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("设置定时器")
        self.setWindowIcon(QIcon('timer.png'))
        # self.setFixedHeight(200)
        # self.setFixedWidth(400)

        self.save_btn = QPushButton('保存')
        self.clear_btn = QPushButton('清空')
        self.exit_btn = QPushButton('保存并关闭')
        self.save_btn.clicked.connect(self.save_data)
        self.clear_btn.clicked.connect(self.clear_data)
        self.exit_btn.clicked.connect(self.exit)

        self.id_label = QLabel('测试编号')
        self.timer_label = QLabel('记录频率（秒/次）')
        self.last_label = QLabel('持续时长（分钟）')

        self.status = QStatusBar()
        self.status.setMinimumWidth(5)

        self.id_data_1 = QLineEdit()
        self.id_data_2 = QLineEdit()
        self.id_data_3 = QLineEdit()
        self.id_data_4 = QLineEdit()
        self.id_data_5 = QLineEdit()
        self.id_data_1.setMinimumWidth(100)
        self.id_data_2.setMinimumWidth(100)
        self.id_data_3.setMinimumWidth(100)
        self.id_data_4.setMinimumWidth(100)
        self.id_data_5.setMinimumWidth(100)
        self.timer_data_1 = QDoubleSpinBox()
        self.timer_data_2 = QDoubleSpinBox()
        self.timer_data_3 = QDoubleSpinBox()
        self.timer_data_4 = QDoubleSpinBox()
        self.timer_data_5 = QDoubleSpinBox()
        self.timer_data_1.setRange(0, 3600)
        self.timer_data_1.setSingleStep(0.1)
        self.timer_data_2.setRange(0, 3600)
        self.timer_data_2.setSingleStep(0.1)
        self.timer_data_3.setRange(0, 3600)
        self.timer_data_3.setSingleStep(0.1)
        self.timer_data_4.setRange(0, 3600)
        self.timer_data_4.setSingleStep(0.1)
        self.timer_data_5.setRange(0, 3600)
        self.timer_data_5.setSingleStep(0.1)
        self.last_data_1 = QSpinBox()
        self.last_data_2 = QSpinBox()
        self.last_data_3 = QSpinBox()
        self.last_data_4 = QSpinBox()
        self.last_data_5 = QSpinBox()
        self.last_data_1.setRange(0, 10000)
        self.last_data_2.setRange(0, 10000)
        self.last_data_3.setRange(0, 10000)
        self.last_data_4.setRange(0, 10000)
        self.last_data_5.setRange(0, 10000)

        self.vbox_id = QVBoxLayout()
        self.vbox_id.addStretch(1)
        self.vbox_id.addWidget(self.id_label, 0, Qt.AlignCenter)
        self.vbox_id.addStretch(1)
        self.vbox_id.addWidget(self.id_data_1, 0, Qt.AlignCenter)
        self.vbox_id.addStretch(1)
        self.vbox_id.addWidget(self.id_data_2, 0, Qt.AlignCenter)
        self.vbox_id.addStretch(1)
        self.vbox_id.addWidget(self.id_data_3, 0, Qt.AlignCenter)
        self.vbox_id.addStretch(1)
        self.vbox_id.addWidget(self.id_data_4, 0, Qt.AlignCenter)
        self.vbox_id.addStretch(1)
        self.vbox_id.addWidget(self.id_data_5, 0, Qt.AlignCenter)

        self.vbox_timer = QVBoxLayout()
        self.vbox_timer.addStretch(1)
        self.vbox_timer.addWidget(self.timer_label, 0, Qt.AlignCenter)
        self.vbox_timer.addStretch(1)
        self.vbox_timer.addWidget(self.timer_data_1, 0, Qt.AlignCenter)
        self.vbox_timer.addStretch(1)
        self.vbox_timer.addWidget(self.timer_data_2, 0, Qt.AlignCenter)
        self.vbox_timer.addStretch(1)
        self.vbox_timer.addWidget(self.timer_data_3, 0, Qt.AlignCenter)
        self.vbox_timer.addStretch(1)
        self.vbox_timer.addWidget(self.timer_data_4, 0, Qt.AlignCenter)
        self.vbox_timer.addStretch(1)
        self.vbox_timer.addWidget(self.timer_data_5, 0, Qt.AlignCenter)

        self.vbox_last = QVBoxLayout()
        self.vbox_last.addStretch(1)
        self.vbox_last.addWidget(self.last_label, 0, Qt.AlignCenter)
        self.vbox_last.addStretch(1)
        self.vbox_last.addWidget(self.last_data_1, 0, Qt.AlignCenter)
        self.vbox_last.addStretch(1)
        self.vbox_last.addWidget(self.last_data_2, 0, Qt.AlignCenter)
        self.vbox_last.addStretch(1)
        self.vbox_last.addWidget(self.last_data_3, 0, Qt.AlignCenter)
        self.vbox_last.addStretch(1)
        self.vbox_last.addWidget(self.last_data_4, 0, Qt.AlignCenter)
        self.vbox_last.addStretch(1)
        self.vbox_last.addWidget(self.last_data_5, 0, Qt.AlignCenter)

        self.hbox_input = QHBoxLayout()
        self.hbox_input.addLayout(self.vbox_id)
        self.hbox_input.addLayout(self.vbox_timer)
        self.hbox_input.addLayout(self.vbox_last)


        self.hbox_btn = QHBoxLayout()
        self.hbox_btn.addWidget(self.status)
        self.hbox_btn.addWidget(self.clear_btn)
        self.hbox_btn.addWidget(self.save_btn)
        self.hbox_btn.addWidget(self.exit_btn)

        self.vbox = QVBoxLayout()
        self.vbox.addLayout(self.hbox_input)
        self.vbox.addStretch(1)
        self.vbox.addLayout(self.hbox_btn)
        self.setLayout(self.vbox)

        # 定时信息dict
        self.record_info = {"id": ['', '', '', '', ''],
                            "timer": [0, 0, 0, 0, 0],
                            "last": [0, 0, 0, 0, 0]}

    def save_data(self):
        id_list = [self.id_data_1.text(), self.id_data_2.text(), self.id_data_3.text(),
                   self.id_data_4.text(), self.id_data_5.text()]
        timer_list = [self.timer_data_1.value(), self.timer_data_2.value(), self.timer_data_3.value(),
                      self.timer_data_4.value(), self.timer_data_5.value()]
        last_list = [self.last_data_1.value(), self.last_data_2.value(), self.last_data_3.value(),
                     self.last_data_4.value(), self.last_data_5.value()]

        self.record_info = {"id": id_list, "timer": timer_list, "last": last_list}
        self.status.showMessage('已保存', 2000)
        self.trans_check.emit()

    def clear_data(self):
        self.id_data_1.clear()
        self.timer_data_1.clear()
        self.last_data_1.clear()
        self.id_data_2.clear()
        self.timer_data_2.clear()
        self.last_data_2.clear()
        self.id_data_3.clear()
        self.timer_data_3.clear()
        self.last_data_3.clear()
        self.id_data_4.clear()
        self.timer_data_4.clear()
        self.last_data_4.clear()
        self.id_data_5.clear()
        self.timer_data_5.clear()
        self.last_data_5.clear()
        self.status.showMessage('已清空', 2000)

    def exit(self):
        self.save_data()
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()

    win.show()
    sys.exit(app.exec_())