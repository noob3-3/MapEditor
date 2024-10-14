import sys
import os
import yaml
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QListWidget, QVBoxLayout,
    QWidget, QLabel, QPushButton, QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsItem, QHBoxLayout,
    QTextEdit, QMessageBox, QDialog
)
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QTransform, QPainter, QPen, QColor


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)  # 允许拖动
        self.setRenderHint(QPainter.Antialiasing)

    def wheelEvent(self, event):
        # 缩放因子
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        # 缩放
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        self.scale(zoom_factor, zoom_factor)


class GridItem(QGraphicsItem):
    def __init__(self, grid_size=0.05, width=200, height=200):
        super().__init__()
        self.grid_size = grid_size
        self.width = width
        self.height = height
        self.pen = QPen(Qt.lightGray)
        self.pen.setWidthF(0.01)  # 设置笔宽为 0.01，使得网格线更细

    def boundingRect(self):
        return QRectF(-self.width / 2, -self.height / 2, self.width, self.height)

    def paint(self, painter, option, widget=None):
        left, top = self.boundingRect().topLeft().x(), self.boundingRect().topLeft().y()
        right, bottom = self.boundingRect().bottomRight().x(), self.boundingRect().bottomRight().y()

        painter.setPen(self.pen)

        for i in range(int(self.width / self.grid_size) + 1):
            x = left + i * self.grid_size
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        for i in range(int(self.height / self.grid_size) + 1):
            y = top + i * self.grid_size
            painter.drawLine(QPointF(left, y), QPointF(right, y))


class DraggableEllipseItem(QGraphicsEllipseItem):
    def __init__(self, parent, color, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setBrush(color)
        self.setPen(QPen(color, 0.001))  # 使用非常细的边框
        self.parent = parent
        self.original_position = self.pos()

        # 使项可选择并接收焦点
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsFocusable)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.record_initial_position(self, self.pos())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.record_final_position_and_store_undo(self, self.pos())
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.parent.delete_item(self)
        else:
            super().keyPressEvent(event)


class MapEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map Editor")
        self.setGeometry(100, 100, 1200, 600)

        # 初始化变量
        self.root_dir = ""
        self.path_data_list = []
        self.undo_stack = []

        # 初始化删除操作的栈和集合
        self.deleted_items_stack = []
        self.deleted_items_set = set()

        # 创建主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部水平布局 (地图和文件列表)
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)

        # 左侧布局 (地图)
        map_layout = QVBoxLayout()
        top_layout.addLayout(map_layout)

        # 图形视图
        self.scene = QGraphicsScene(-100, -100, 200, 200)  # 设置场景大小为200x200米
        self.graphics_view = CustomGraphicsView(self.scene, self)
        map_layout.addWidget(self.graphics_view)

        # 添加网格项
        self.grid_item = GridItem(grid_size=0.05, width=200, height=200)
        self.scene.addItem(self.grid_item)

        # 右侧布局 (文件列表和按钮)
        control_layout = QVBoxLayout()

        # 设置右侧布局的最大宽度
        control_layout.setSpacing(10)  # 调整控件之间的间距
        control_layout_widget = QWidget()
        control_layout_widget.setLayout(control_layout)
        control_layout_widget.setMaximumWidth(200)  # 设置最大宽度
        top_layout.addWidget(control_layout_widget)

        # 文件列表
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemClicked.connect(self.load_yaml_files)
        control_layout.addWidget(self.file_list_widget)

        # 按钮
        load_button = QPushButton("选择文件夹", self)
        load_button.clicked.connect(self.choose_folder)
        control_layout.addWidget(load_button)

        save_button = QPushButton("保存修改", self)
        save_button.clicked.connect(self.save_yaml_files)
        control_layout.addWidget(save_button)

        # 状态标签
        self.status_label = QLabel("")
        control_layout.addWidget(self.status_label)

        # 日志框
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setMaximumHeight(100)  # 设置最大高度为100像素
        main_layout.addWidget(self.log_text_edit)

        # 启用键盘事件处理
        self.setFocusPolicy(Qt.StrongFocus)

        # 添加状态栏
        self.statusBar().showMessage('Ready')

        # 添加菜单项
        menubar = self.menuBar()
        help_menu = menubar.addMenu('Help')
        about_action = help_menu.addAction('About')
        about_action.triggered.connect(self.show_about_dialog)

    def show_about_dialog(self):
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle("About")

        layout = QVBoxLayout(about_dialog)

        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setText(
            "<h3>Map Editor</h3>"
            "<p>Version 1.0</p>"
            "<p>Developed by: noob3-3</p>"
            '<p>GitHub: <a href="https://github.com/noob3-3/MapEditor.git">https://github.com/noob3-3/MapEditor.git</a></p>'
            "<p>This application uses Qt for Python (PySide2/PyQt5).</p>"
            "<p>Qt is a free and open-source widget toolkit for creating graphical user interfaces.</p>"
        )
        layout.addWidget(label)

        about_dialog.setLayout(layout)
        about_dialog.exec_()

    def log_message(self, message):
        self.log_text_edit.append(message)

    def record_initial_position(self, item, pos):
        # 记录初始位置
        self.initial_position = pos

    def record_final_position_and_store_undo(self, item, new_pos):
        # 将初始位置和新位置存储到撤销栈
        self.undo_stack.append(('move', item, self.initial_position, new_pos))
        self.log_message(f"Moved item from {self.initial_position} to {new_pos}")

    def delete_item(self, item):
        # 从场景中移除项并添加到删除栈
        self.scene.removeItem(item)
        self.deleted_items_stack.append((item, item.scenePos()))
        self.deleted_items_set.add(item)
        self.undo_stack.append(('delete', item))
        self.log_message(f"Deleted item at position {item.scenePos()}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Z and (event.modifiers() & Qt.ControlModifier):
            self.undo_action()
        else:
            super().keyPressEvent(event)

    def undo_action(self):
        if not self.undo_stack:
            return

        action = self.undo_stack.pop()

        if action[0] == 'move':
            _, item, old_pos, _ = action
            item.setPos(old_pos)
            self.log_message(f"Undo move: item moved back to {old_pos}")
        elif action[0] == 'delete':
            item, pos = self.deleted_items_stack.pop()
            self.scene.addItem(item)
            item.setPos(pos)
            self.deleted_items_set.remove(item)
            self.log_message(f"Undo delete: item restored to {pos}")

    def choose_folder(self):
        self.root_dir = QFileDialog.getExistingDirectory(self, "选择目录")
        if self.root_dir:
            self.load_files()

    def load_files(self):
        self.file_list_widget.clear()
        for file_name in os.listdir(self.root_dir):
            if file_name.endswith('.yaml'):
                self.file_list_widget.addItem(file_name)

    def load_yaml_files(self, item):
        file_name = item.text()

        # 检查文件是否已存在于 path_data_list 中
        for existing_file_name, _ in self.path_data_list:
            if existing_file_name == file_name:
                return  # 文件已存在，不重复加载

        file_path = os.path.join(self.root_dir, file_name)

        with open(file_path, 'r') as file:
            path_data = yaml.load(file, Loader=yaml.FullLoader)
            len_path_data = len(path_data['poses'])
            print_msg = f"加载文件名={file_name} 轨迹长度={len_path_data}"
            self.log_message(print_msg)
            self.path_data_list.append((file_name, path_data))

        self.display_points()
        self.log_message(f"Loaded file: {file_name}")

    def display_points(self):
        # 移除所有已有的点
        items_to_remove = [item for item in self.scene.items() if isinstance(item, QGraphicsEllipseItem)]
        for item in items_to_remove:
            self.scene.removeItem(item)

        # 定义颜色列表
        colors = [QColor('red'), QColor('blue'), QColor('green'), QColor('yellow'), QColor('cyan')]

        # 显示每个加载文件中的点
        for idx, (file_name, path_data) in enumerate(self.path_data_list):
            if not path_data or 'poses' not in path_data:
                continue

            color = colors[idx % len(colors)]  # 轮询使用颜色

            for pose in path_data['poses']:
                position = pose['position']
                x, y = position['x'], position['y']
                ellipse = DraggableEllipseItem(self, color, -0.05, -0.05, 0.1, 0.1)  # 调整后的固定大小
                ellipse.setPos(x, y)  # 设置椭圆的位置
                self.scene.addItem(ellipse)

    def save_yaml_files(self):
        for file_name, path_data in self.path_data_list:
            if not path_data or 'poses' not in path_data:
                continue

            # 获取当前场景中的所有可拖动椭圆
            current_items = [item for item in self.scene.items() if isinstance(item, DraggableEllipseItem)]

            updated_poses = []
            for item in current_items:
                if item in self.deleted_items_set:
                    continue  # 跳过已删除的项
                pos = item.scenePos()
                updated_poses.append({
                    'position': {'x': pos.x(), 'y': pos.y()}
                })

            # 更新path_data中的poses
            path_data['poses'] = updated_poses
            len_path_data = len(path_data['poses'])
            print_msg = f"保存文件名={file_name} 轨迹长度={len_path_data}"
            self.log_message(print_msg)
            file_path = os.path.join(self.root_dir, file_name)
            with open(file_path, 'w') as file:
                yaml.dump(path_data, file)

        self.log_message("Saved modifications to files")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MapEditor()
    window.show()
    sys.exit(app.exec_())
