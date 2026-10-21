# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import cv2
from numpy import frombuffer, uint8, array, random
import numpy as np
import time

from math import dist
from cached_property import cached_property
from win32gui import (GetWindowText, EnumWindows, FindWindow, FindWindowEx,
                      IsWindow, GetWindowRect, GetWindowDC, DeleteObject,
                      SetForegroundWindow, IsWindowVisible, GetDC, GetParent,
                      EnumChildWindows, SetForegroundWindow, GetClientRect)
from win32con import (SRCCOPY, DESKTOPHORZRES, DESKTOPVERTRES, WM_LBUTTONUP,
                      WM_LBUTTONDOWN, WM_ACTIVATE, WA_ACTIVE, MK_LBUTTON,
                      WM_NCHITTEST, WM_SETCURSOR, HTCLIENT, WM_MOUSEMOVE,
                      WM_PARENTNOTIFY, WM_MOUSEACTIVATE, WM_MOUSEWHEEL,
                      WM_SETFOCUS, WM_CAPTURECHANGED)
from win32ui import CreateDCFromHandle, CreateBitmap
from win32api import GetSystemMetrics, SendMessage, MAKELONG, PostMessage
from win32con import SRCCOPY


from module.base.cBezier import human_track
from module.device.method.desktop_impl import dpi_awareness
from module.exception import RequestHumanTakeover, ScriptError
from module.base.decorator import Config
from module.base.timer import timer
from module.logger import logger
from module.device.handle import Handle, window_scale_rate, EmulatorFamily




class Window(Handle):

    def __init__(self, *args, **kwargs):
        logger.info("Window init")
        super().__init__(*args, **kwargs)

    def screenshot_window_background(self):
        """
        后台截屏
        :return:
        """
        if getattr(self, 'is_desktop_window', False):
            return self.screenshot_desktop_bitblt()

        widthScreen, heightScreen = self.screenshot_size
        # 返回句柄窗口的设备环境，覆盖整个窗口，包括非客户区，标题栏，菜单，边框
        hwndDc = GetWindowDC(self.screenshot_handle_num)
        # 创建设备描述表
        mfcDc = CreateDCFromHandle(hwndDc)
        # 创建内存设备描述表
        saveDc = mfcDc.CreateCompatibleDC()
        # 创建位图对象准备保存图片
        saveBitMap = CreateBitmap()
        # 为bitmap开辟存储空间
        saveBitMap.CreateCompatibleBitmap(mfcDc, widthScreen, heightScreen)
        # 将截图保存到saveBitMap中
        saveDc.SelectObject(saveBitMap)
        # 保存bitmap到内存设备描述表
        saveDc.BitBlt((0, 0), (widthScreen, heightScreen), mfcDc, (0, 0), SRCCOPY)

        # 保存图像
        signedIntsArray = saveBitMap.GetBitmapBits(True)
        imgSrceen = frombuffer(signedIntsArray, dtype='uint8')
        imgSrceen.shape = (heightScreen, widthScreen, 4)
        # 这点很重要 在alas中图片以np.ndarray（RGB）的顺序存储。但是opencv是以BGR
        imgSrceen = cv2.cvtColor(imgSrceen, cv2.COLOR_BGR2RGB)
        # imgSrceen = cv2.resize(imgSrceen, (win_size[0], win_size[1]))
        # 很奇怪的

        # # 测试显示截图图片
        # cv2.namedWindow('imgSrceen')  # 命名窗口
        # cv2.imshow("imgSrceen", imgSrceen)  # 显示
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()

        # 内存释放
        DeleteObject(saveBitMap.GetHandle())
        saveDc.DeleteDC()
        mfcDc.DeleteDC()
        return imgSrceen

    def screenshot_desktop_bitblt(self):
        """Capture the desktop game client from its DPI-aware client area."""
        self.desktop_window_restore_if_minimized()
        self._desktop_assert_window_pos(self.root_handle_num)
        with dpi_awareness():
            client_rect = GetClientRect(self.screenshot_handle_num)
            width_screen = client_rect[2] - client_rect[0]
            height_screen = client_rect[3] - client_rect[1]
            if width_screen <= 0 or height_screen <= 0:
                raise RequestHumanTakeover('Desktop client window is minimized, screenshot unavailable')
            hwnd_dc = GetDC(self.screenshot_handle_num)
            mfc_dc = CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_bitmap = CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width_screen, height_screen)
            save_dc.SelectObject(save_bitmap)
            save_dc.BitBlt((0, 0), (width_screen, height_screen), mfc_dc, (0, 0), SRCCOPY)
            image_bytes = save_bitmap.GetBitmapBits(True)
            image = frombuffer(image_bytes, dtype='uint8')
            image.shape = (height_screen, width_screen, 4)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
        target_width, target_height = self.screenshot_size
        if (width_screen, height_screen) != (target_width, target_height):
            image = cv2.resize(image, (target_width, target_height))
        return image

    @cached_property
    def control_handle_list(self) -> list:
        """
        不同的模拟器需要的子句柄不同
        mumu模拟器的控制需要 根窗口和第一个子窗口
        雷电模拟器只需要TheRender窗口
        夜神模拟器
        :return:
        """
        result = []
        if getattr(self, 'is_desktop_window', False):
            return [self.root_handle_num]
        if self.emulator_family == EmulatorFamily.FAMILY_MUMU:
            result.append(self.root_node.num)
            result.append(self.root_node.children[0].num)
            return result
        elif self.emulator_family == EmulatorFamily.FAMILY_NOX:
            result.append(self.root_node.num)
            try:
                result.append(self.root_node.children[1].num)
                result.append(self.root_node.children[1].children[1].num)
                result.append(self.root_node.children[1].children[1].children[0].num)
            except:
                result.append(self.root_node.children[2].num)
                result.append(self.root_node.children[2].children[1].num)
                result.append(self.root_node.children[2].children[1].children[0].num)
            return result
        elif self.emulator_family == EmulatorFamily.FAMILY_LD:
            result.append(self.root_node.children[0].num)
            return result
        elif self.emulator_family == EmulatorFamily.FAMILY_MEMU:
            pass
        elif self.emulator_family == EmulatorFamily.FAMILY_BLUESTACKS:
            pass

    @cached_property
    def mumu_head_height(self):
        """
        不同mumu模拟器的头部高度不同
        :return:
        """
        father_win_Rect = GetWindowRect(self.control_handle_list[0])
        father_height: int = father_win_Rect[3] - father_win_Rect[1]  # 下y - 上y 计算高度
        children_win_Rect = GetWindowRect(self.control_handle_list[1])
        children_height: int = children_win_Rect[3] - children_win_Rect[1]  # 下y - 上y 计算高度
        height = father_height - children_height
        if int(height * self.window_scale_rate) == 37:
            # 说明是mumu模拟器 不做处理
            pass
        if int(height * self.window_scale_rate) == 45:
            # 说明是mumu12模拟器 不做处理
            pass
        logger.info(f"Mumu emulator head height: {height}")
        return height

    def click_window_message(self, x: int, y: int, fast: bool = False):
        """

        :param x:
        :param y:
        :param fast:
        :return:
        """
        if getattr(self, 'is_desktop_window', False):
            return self.click_desktop_window_message(x, y, fast)

        # 我不知道为什么的使用的pywin32==306的版本会导致获取的图片的是(1024, 576)
        # 所有我在点击的时候会除以这个缩放比例
        # 但是后面发现又不是影响的很奇怪

        x = int(x / self.window_scale_rate)
        y = int(y / self.window_scale_rate)
        if fast:
            press_time: float = (random.randint(10, 40)) / 1000.0
        else:
            press_time: float = (random.randint(100, 200)) / 1000.0
        emulator_type = len(self.control_handle_list)
        if emulator_type == 2:  # mumu模拟器
            SendMessage(self.control_handle_list[0], WM_ACTIVATE, WA_ACTIVE, 0)  # 激活窗口
            # SendMessage(self.control_handle_list[1], WM_ACTIVATE, WA_ACTIVE, 0)  # 激活窗口
            # SendMessage(self.control_handle_list[0], WM_LBUTTONDOWN, 0, MAKELONG(x, y+self.mumu_head_height))  # 模拟鼠标按下 先是父窗口 上面的框高度是57
            # mumu12模拟器 V3.5.16 之后后可以用下面的方式
            SendMessage(self.control_handle_list[1], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            time.sleep(press_time)
            SendMessage(self.control_handle_list[1], WM_LBUTTONUP, 0, MAKELONG(x, y))  # 模拟鼠标弹起 后是子窗口
        elif emulator_type > 2:  # 夜神模拟器
            SendMessage(self.control_handle_list[0], WM_LBUTTONDOWN, 0, MAKELONG(x, y))  # 模拟鼠标按下 先是父窗口 上面的框高度是57
            SendMessage(self.control_handle_list[1], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            SendMessage(self.control_handle_list[2], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            SendMessage(self.control_handle_list[3], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            time.sleep(press_time)
            SendMessage(self.control_handle_list[3], WM_LBUTTONUP, 0, MAKELONG(x, y))  # 模拟鼠标弹起 后是子窗口
        elif emulator_type == 1:  # 雷电模拟器
            clickPos = MAKELONG(x, y)
            SendMessage(self.control_handle_list[0], WM_LBUTTONDOWN, 0, clickPos)
            time.sleep(press_time)
            SendMessage(self.control_handle_list[0], WM_LBUTTONUP, 0, clickPos)

    def desktop_message_coord(self, x, y) -> tuple:
        """Convert 1280x720 asset coordinates to the process's virtual message space."""
        target_width, target_height = self.screenshot_size
        virtual_width, virtual_height = self.desktop_client_size_virtual()
        return int(round(x * virtual_width / target_width)), int(round(y * virtual_height / target_height))

    def _desktop_press(self, x: int, y: int, press_time: float) -> None:
        """Send hover, press and release messages to the native desktop client."""
        self.desktop_window_restore_if_minimized()
        hwnd = self.root_handle_num
        self.move_desktop_window_message(x, y)
        lparam = MAKELONG(*self.desktop_message_coord(x, y))
        PostMessage(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(press_time)
        PostMessage(hwnd, WM_LBUTTONUP, 0, lparam)
        SendMessage(hwnd, WM_CAPTURECHANGED, 0, 0)
        PostMessage(hwnd, WM_MOUSEMOVE, 0, lparam)

    def click_desktop_window_message(self, x: int, y: int, fast: bool = False):
        """Click the native client without bringing its window to the foreground."""
        press_time = (random.randint(10, 25) if fast else random.randint(30, 60)) / 1000.0
        self._desktop_press(x, y, press_time)

    def long_click_desktop_window_message(self, x: int, y: int, duration: float):
        """Long-click the native client in the background."""
        self._desktop_press(x, y, duration)

    def move_desktop_window_message(self, x: int, y: int) -> None:
        """Move the native client's hover cursor along a bounded human-like path."""
        hwnd = self.root_handle_num
        start = getattr(self, '_desktop_cursor', None)
        target = (int(x), int(y))

        def post_move(px, py):
            PostMessage(hwnd, WM_MOUSEMOVE, 0, MAKELONG(*self.desktop_message_coord(px, py)))

        if start is None or start == target:
            post_move(*target)
            self._desktop_cursor = target
            return
        trace = human_track(start, target, interval=self.DESKTOP_MOVE_STEP)
        if len(trace) > self.DESKTOP_MOVE_MAX_POINTS:
            step = len(trace) / self.DESKTOP_MOVE_MAX_POINTS
            trace = [trace[int(i * step)] for i in range(self.DESKTOP_MOVE_MAX_POINTS)]
        for px, py in trace:
            post_move(px, py)
        post_move(*target)
        self._desktop_cursor = target

    def long_click_window_message(self, x: int, y: int, duration: float):
        """

        :param x:
        :param y:
        :param duration: 持续时间 单位秒
        :return:
        """
        if getattr(self, 'is_desktop_window', False):
            return self.long_click_desktop_window_message(x, y, duration)

        # 我不知道为什么的使用的pywin32==306的版本会导致获取的图片的是(1024, 576)
        # 所有我在点击的时候会除以这个缩放比例
        x = int(x / self.window_scale_rate)
        y = int(y / self.window_scale_rate)

        emulator_type = len(self.control_handle_list)
        if self.emulator_family == EmulatorFamily.FAMILY_MUMU:  # mumu模拟器
            SendMessage(self.control_handle_list[1], WM_ACTIVATE, WA_ACTIVE, 0)  # 激活窗口
            # SendMessage(self.control_handle_list[0], WM_LBUTTONDOWN, 0, MAKELONG(x, y+self.mumu_head_height))  # 模拟鼠标按下 先是父窗口 上面的框高度是57
            SendMessage(self.control_handle_list[1], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            time.sleep(duration)  # 长按时间1000ms-1500ms
            SendMessage(self.control_handle_list[1], WM_LBUTTONUP, 0, MAKELONG(x, y))  # 模拟鼠标弹起 后是子窗口
        elif emulator_type > 2:  # 夜神模拟器
            SendMessage(self.control_handle_list[0], WM_LBUTTONDOWN, 0, MAKELONG(x, y))  # 模拟鼠标按下 先是父窗口 上面的框高度是57
            SendMessage(self.control_handle_list[1], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            SendMessage(self.control_handle_list[2], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            SendMessage(self.control_handle_list[3], WM_LBUTTONDOWN, 0, MAKELONG(x, y))
            time.sleep(duration)  # 长按时间1000ms-1500ms
            SendMessage(self.control_handle_list[3], WM_LBUTTONUP, 0, MAKELONG(x, y))  # 模拟鼠标弹起 后是子窗口
        elif emulator_type == 1:  # 雷电模拟器
            clickPos = MAKELONG(x, y)
            SendMessage(self.control_handle_list[0], WM_LBUTTONDOWN, 0, clickPos)  # 模拟鼠标按下
            time.sleep(duration)  # 长按时间1000ms-1500ms
            SendMessage(self.control_handle_list[0], WM_LBUTTONUP, 0, clickPos)  # 模拟鼠标弹起

    # @timer
    def swipe_window_message(self, startPos: list, endPos: list) -> None:
        """
        后台滑动
        :param startPos:
        :param endPos:
        :return:
        """
        if getattr(self, 'is_desktop_window', False):
            return self.swipe_desktop_window_message(startPos, endPos)

        # 生成的坐标点列表
        interval: int = 10  # 每次移动的间隔时间
        trace = human_track(startPos, endPos, interval=interval)
        # 使用生成的点列表进行拖拽
        handleNum = None
        if self.emulator_family == EmulatorFamily.FAMILY_MUMU:  # mumu模拟器
            handleNum = self.control_handle_list[1]
        elif self.emulator_family == EmulatorFamily.FAMILY_NOX:  # 夜神模拟器
            handleNum = self.control_handle_list[3]
        elif self.emulator_family == EmulatorFamily.FAMILY_LD:  # 雷电模拟器
            handleNum = self.control_handle_list[0]

        # 激活窗口
        # SendMessage(self.control_handle_list[0], WM_PARENTNOTIFY, WM_LBUTTONDOWN, tmpPos)
        # SendMessage(self.control_handle_list[0], WM_MOUSEACTIVATE, WM_LBUTTONDOWN, tmpPos)
        # PostMessage(handleNum, WM_ACTIVATE, WA_ACTIVE, 0)

        # 先移动到第一个点
        tmpPos = MAKELONG(trace[0][0], trace[0][1])
        SendMessage(handleNum, WM_NCHITTEST, 0, tmpPos)
        SendMessage(handleNum, WM_SETCURSOR, handleNum, MAKELONG(HTCLIENT, WM_LBUTTONDOWN))
        PostMessage(handleNum, WM_LBUTTONDOWN, 0, tmpPos)

        # 一点一点移动鼠标
        manual_control: int = 3  # 手动控制最后几个点的数量
        total_len: int = len(trace)
        for index, pos in enumerate(trace):
            lparam = MAKELONG(pos[0], pos[1])
            PostMessage(handleNum, WM_MOUSEMOVE, MK_LBUTTON, lparam)
            if manual_control >= total_len - index:
                time.sleep(0.08)
            else:
                time.sleep((interval + random.randint(-2, 2)) / 1000.0)

        # 最后释放鼠标
        time.sleep(0.05)
        end_lparam = MAKELONG(trace[-1][0], trace[-1][1])
        PostMessage(handleNum, WM_LBUTTONUP, 0, end_lparam)

    def swipe_desktop_window_message(self, startPos: list, endPos: list) -> None:
        """Drag in the desktop client with hover-aware window messages."""
        self.desktop_window_restore_if_minimized()
        hwnd = self.root_handle_num
        interval = 10
        trace = human_track(startPos, endPos, interval=interval)
        self.move_desktop_window_message(startPos[0], startPos[1])
        start_lparam = MAKELONG(*self.desktop_message_coord(startPos[0], startPos[1]))
        PostMessage(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, start_lparam)
        total_len = len(trace)
        for index, pos in enumerate(trace):
            lparam = MAKELONG(*self.desktop_message_coord(pos[0], pos[1]))
            PostMessage(hwnd, WM_MOUSEMOVE, MK_LBUTTON, lparam)
            time.sleep(0.08 if 3 >= total_len - index else (interval + random.randint(-2, 2)) / 1000.0)
        time.sleep(0.05)
        end_lparam = MAKELONG(*self.desktop_message_coord(endPos[0], endPos[1]))
        PostMessage(hwnd, WM_LBUTTONUP, 0, end_lparam)
        SendMessage(hwnd, WM_CAPTURECHANGED, 0, 0)
        self._desktop_cursor = (int(endPos[0]), int(endPos[1]))

    def swipe_vector_window_message2(self, startPos: list, endPos: list) -> None:
        """
        后台滑动, 直线滑动
        :param startPos:
        :param endPos:
        :return:
        """
        # 生成的坐标点列表
        interval: int = 8  # 每次移动的间隔时间
        numberList: int = int(dist(startPos, endPos) / (1.5 * interval))  # 表示每毫秒移动1.5个像素点， 总的时间除以每个点10ms就得到总的点的个数

        def generate_points(start_pos: list, end_pos: list, number: int) -> list:
            # 确定两点之间的步长
            step_x = (end_pos[0] - start_pos[0]) / (number + 1)
            step_y = (end_pos[1] - start_pos[1]) / (number + 1)
            # 生成中间点坐标列表
            points = []
            for i in range(number):
                x = start_pos[0] + step_x * (i + 1)
                y = start_pos[1] + step_y * (i + 1)
                points.append((x, y))
            # 添加起始点和最终点到列表中
            points.insert(0, tuple(start_pos))
            points.append(tuple(end_pos))
            return points

        trace: list = generate_points(start_pos=startPos, end_pos=endPos, number=numberList)

        # 使用生成的点列表进行拖拽
        emulator_type = len(self.control_handle_list)
        if emulator_type == 1:  # 雷电模拟器
            handleNum = self.control_handle_list[0]
        elif emulator_type == 2:  # mumu模拟器
            handleNum = self.control_handle_list[1]
        elif emulator_type > 2:  # 夜神模拟器
            handleNum = self.control_handle_list[3]
        PostMessage(handleNum, WM_ACTIVATE, WA_ACTIVE, 0)  # 激活窗口
        # 先移动到第一个点
        tmpPos = MAKELONG(trace[0][0], trace[0][1])
        SendMessage(handleNum, WM_NCHITTEST, 0, tmpPos)
        SendMessage(handleNum, WM_SETCURSOR, handleNum, MAKELONG(HTCLIENT, WM_LBUTTONDOWN))
        PostMessage(handleNum, WM_LBUTTONDOWN, MK_LBUTTON, tmpPos)
        # 一点一点移动鼠标
        for pos in trace:
            tmpPos = MAKELONG(pos[0], pos[1])
            PostMessage(handleNum, WM_MOUSEMOVE, MK_LBUTTON, tmpPos)
            time.sleep((interval + random.randint(-2, 2)) / 1000.0)
        # 最后释放鼠标
        tmpPos = MAKELONG(trace[-1][0], trace[-1][1])
        PostMessage(handleNum, WM_LBUTTONUP, 0, tmpPos)

    def scroll_window_message(self, x: int, y: int, delta: int=-120) -> None:
        """
        弃置
        https://github.com/runhey/OnmyojiAutoScript/issues/43
        :param x:
        :param y:
        :param delta:
        :return:
        """
        wparam = MAKELONG(0, delta)
        lparam = MAKELONG(x, y)
        handle_num = None
        if self.emulator_family == EmulatorFamily.FAMILY_MUMU:  # mumu模拟器
            handle_num = self.control_handle_list[1]

        elif self.emulator_family == EmulatorFamily.FAMILY_NOX:  # 夜神模拟器
            handle_num = self.control_handle_list[3]
        elif self.emulator_family == EmulatorFamily.FAMILY_LD:  # 雷电模拟器
            handle_num = self.control_handle_list[0]

        SetForegroundWindow(handle_num)
        time.sleep(2)
        # SendMessage(handle_num, WM_SETFOCUS, 0, 0)
        # SendMessage(handle_num, WM_ACTIVATE, WA_ACTIVE, 0)
        # SendMessage(handle_num, WM_MOUSEACTIVATE, WM_LBUTTONDOWN, lparam)


        SendMessage(handle_num, WM_NCHITTEST, 0, lparam)
        SendMessage(handle_num, WM_SETCURSOR, handle_num, lparam)
        PostMessage(handle_num, WM_MOUSEMOVE, 0, lparam)
        self.click_window_message(x, y)

        for i in range(5):
            PostMessage(handle_num, WM_SETCURSOR, handle_num, lparam)
            PostMessage(handle_num, WM_MOUSEMOVE, 0, lparam)
            PostMessage(handle_num, WM_MOUSEWHEEL, wparam, lparam)
            time.sleep(0.5)
        # 抄网上的
        # SendMessage(handle_num, WM_NCHITTEST, 0, lparam)





if __name__ == "__main__":
    w = Window(config='oas1')
    # img = w.screenshot_window_background()
    # handle = 459852
    # wparam = MAKELONG(0, -120)
    # lparam = MAKELONG(300, 300)
    # PostMessage(handle, WM_MOUSEWHEEL, wparam, lparam)

    w.long_click_window_message(142, 310, 1.5)


