from typing import Any, List, Optional, TypeAlias

import cv2
import numpy as np
import pyautogui
import win32api
import win32con
import win32gui
import win32process
import win32ui
from PIL import Image

from ...Structure import ROI
from ...Typehints import (
    GlobalsDict,
    RegionDict,
    ROI_DebugDict,
    WindowDict,
    WindowLocationDict,
)
from ..Controller import InputController, LogLevel, global_log_manager
from ..Exceptions.crash import (
    ActionTypeError,
    DebugError,
    IllegalWindowAreaError,
    MissingRequiredError,
    MultipleMatchedError,
    RegionError,
    TemplateError,
    WindowNotFoundError,
)
from ..Exceptions.ignorable import MatchingError
from ..executor import Executor, Job, JobExecutor

PILImage: TypeAlias = Image.Image


@JobExecutor.register("ROI")
class ROIExecutor(Executor):
    def __init__(self, job: Job, globals: GlobalsDict) -> None:
        self.job: Job = job
        self.globals: GlobalsDict = globals

    def __capture_screen(self, roi: ROI) -> WindowLocationDict:
        region: Optional[RegionDict] = roi.get("region", None)
        if region is None:
            return WindowLocationDict(
                left=0,
                top=0,
                mat=pyautogui.screenshot(),
            )
        cap_x: int = int(region.get("x", 0))
        cap_y: int = int(region.get("y", 0))
        cap_width: int = int(region.get("width", pyautogui.size().width))
        cap_height: int = int(region.get("height", pyautogui.size().height))

        return WindowLocationDict(
            left=cap_x,
            top=cap_y,
            mat=pyautogui.screenshot(region=(cap_x, cap_y, cap_width, cap_height)),
        )

    def __capture_window(self, roi: ROI) -> WindowLocationDict:
        window: WindowDict = roi.get("window", {})
        # 匹配条件
        target_title = window.get("title", "")
        target_class_name = window.get("class_name", "")
        target_process = window.get("process", "")
        if not (target_title or target_class_name or target_process):
            raise MissingRequiredError(
                "At least one of title, class_name or process must be specified."
            )

        # 获取所有窗口的句柄
        def hwnd_callback(hWnd: int, param: List[int]) -> None:
            param.append(hWnd)

        hWnd_list: List[int] = []
        matched: int = -1
        win32gui.EnumWindows(hwnd_callback, hWnd_list)

        for hWnd in hWnd_list:
            # 窗口过滤
            if not win32gui.IsWindowVisible(hWnd):
                continue
            ## title
            title: str = win32gui.GetWindowText(hWnd)
            if not title:
                continue

            ## class_name
            class_name: Optional[str] = win32gui.GetClassName(hWnd)

            ## process
            process_id = win32process.GetWindowThreadProcessId(hWnd)[1]
            h_process = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                False,
                process_id,
            )
            path: str = str(win32process.GetModuleFileNameEx(h_process, 0))  # type: ignore[union-attr]
            process: str = path.split("\\")[-1] if path else ""
            win32api.CloseHandle(h_process)

            if (
                (not target_title or title == target_title)
                and (not target_class_name or class_name == target_class_name)
                and (not target_process or process == target_process)
            ):
                if matched != -1:
                    raise MultipleMatchedError(
                        job=self.job,
                        message=f"匹配到多个窗口, 请指定更精确的窗口参数.",
                    )
                matched = hWnd
        if matched == -1:
            raise WindowNotFoundError(
                job=self.job,
                message=f"未找到匹配的窗口: title={target_title}, class_name={target_class_name}, process={target_process}",
            )
        # 获取窗口坐标
        rect = win32gui.GetWindowRect(matched)
        win_left, win_top, win_right, win_bottom = rect

        # region
        inf = float("inf")
        region: RegionDict = roi.get("region", {})
        region_x: int = int(max(region.get("x", -inf), 0))
        region_y: int = int(max(region.get("y", -inf), 0))
        cap_x = win_left + region_x
        cap_y = win_top + region_y
        cap_width: int = int(min(region.get("width", inf), win_right - cap_x))
        cap_height: int = int(min(region.get("height", inf), win_bottom - cap_y))
        cap = (cap_x, cap_y, cap_width, cap_height)

        allow_out_of_screen: bool = window.get("allow_out_of_screen", False)
        screen_size = pyautogui.size()
        if (
            cap_x + cap_width < 0
            or cap_y + cap_height < 0
            or cap_x > screen_size.width
            or cap_y > screen_size.height
            or (cap_width <= 0)
            or (cap_height <= 0)
        ):
            if not allow_out_of_screen:
                raise IllegalWindowAreaError(
                    job=self.job,
                    message=f"窗口区域无效: {cap}",
                )
            global_log_manager.log(
                f"窗口区域无效: {cap}, 允许超出屏幕: {allow_out_of_screen}",
                [LogLevel.WARNING],
                debug=self.globals.get("debug", False),
            )

        if window.get("allow_overlay", False):
            screenshot: Image.Image = pyautogui.screenshot(region=cap)
        else:
            hWndDC = win32gui.GetWindowDC(matched)
            mfcDC = win32ui.CreateDCFromHandle(hWndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, cap_width, cap_height)
            saveDC.SelectObject(saveBitMap)
            saveDC.BitBlt(
                (0, 0),
                (cap_width, cap_height),
                mfcDC,
                (region_x, region_y),
                win32con.SRCCOPY,
            )

            bmpinfo = saveBitMap.GetInfo()  # type: ignore[union-attr]
            bmpstr = saveBitMap.GetBitmapBits(True)
            screenshot = Image.frombuffer(
                "RGB",
                (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),  # type: ignore[union-attr]
                bmpstr,
                "raw",
                "BGRX",
                0,
                1,
            )
        return WindowLocationDict(
            left=win_left + region_x,
            top=win_top + region_y,
            mat=screenshot,
        )

    def __capture(self, roi: ROI) -> WindowLocationDict:
        # 读取对象窗口参数
        window: Optional[WindowDict] = roi.get("window", None)
        if window is None:
            return self.__capture_screen(roi)
        else:
            return self.__capture_window(roi)

    def __execute_debug(self, roi: ROI, *, mat: PILImage) -> None:
        debug: Optional[ROI_DebugDict] = roi.get("debug", {})
        if debug and not self.globals.get("debug", False):
            raise DebugError(job=self.job, message="Debugging is disabled in globals.")
        elif debug is None:
            return

        if debug.get("display_screenshot", False):
            mat.show()

    def main(self, roi: ROI) -> str:
        wld: WindowLocationDict = self.__capture(roi)
        mat = cv2.cvtColor(np.array(wld["mat"]), cv2.COLOR_RGB2BGR)

        # debug
        self.__execute_debug(roi, mat=wld["mat"])

        # 目标偏移量
        offset_x: int = wld["left"]
        offset_y: int = wld["top"]

        # 读取模板图
        template_path: str = roi["image"]["path"]
        confidence: float = roi["image"].get("confidence", 1.0)
        template = cv2.imread(template_path)
        if template is None:  # type: ignore[union-attr]
            raise TemplateError(
                job=self.job,
                message=f"Template image not found at path: {template_path}",
            )
        if mat.shape[0] < template.shape[0] or mat.shape[1] < template.shape[1]:
            raise RegionError(
                job=self.job,
                message="ROI region is smaller than the template image, cannot match.",
            )

        # 匹配
        mat_gray = cv2.cvtColor(mat, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(mat_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < confidence:
            raise MatchingError(
                job=self.job,
                message=f"No match found in region with confidence >= {confidence}",
            )

        # 计算匹配位置
        matched_left_top = (
            max_loc[0] + offset_x,
            max_loc[1] + offset_y,
        )
        matched_center = (
            matched_left_top[0] + template_gray.shape[1] // 2,
            matched_left_top[1] + template_gray.shape[0] // 2,
        )

        # log
        global_log_manager.log(
            f"ROI detected at {matched_center} with confidence {max_val}",
            [LogLevel.DEBUG],
            debug=self.globals.get("debug", False),
        )

        # action Factory
        if roi.get("type") == "DetectOnly":
            return f"Detected at {matched_center} with confidence {max_val}"

        elif roi.get("type") == "MoveMouse":
            # 移动鼠标
            duration: int = roi.get("duration", 0)
            InputController.move_to(
                x=matched_center[0],
                y=matched_center[1],
                duration=duration,
                debug=self.globals.get("debug", False),
                ignore=self.globals.get("ignore", False),
            )

            return f"Matched at {matched_center}" f", confidence: {max_val}"
        else:
            raise ActionTypeError(
                job=self.job,
                message=f"Unsupported ROI type: {roi.get('type')}",
            )

    def execute(self, *args: Any, **kwargs: Any) -> str:
        roi: Optional[ROI] = self.job.get("roi", None)
        if roi is None:
            raise MissingRequiredError("No ROI found in the job to execute.", self.job)
        return self.main(roi)
