from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Image(BaseModel):
    path: str = Field(..., description="图片路径, 支持相对或绝对路径")
    confidence: Optional[float] = Field(
        ..., ge=0, le=1, description="置信度, 0~1, 默认1.0"
    )


class Region(BaseModel):
    x: int = Field(..., description="区域左上角X坐标, 像素值")
    y: int = Field(..., description="区域左上角Y坐标, 像素值")
    width: int = Field(..., gt=0, description="区域宽度, 像素值, 必须大于0")
    height: int = Field(..., gt=0, description="区域高度, 像素值, 必须大于0")


class Position(BaseModel):
    type: Literal["Absolute", "Relative"] = Field(
        "Relative", description="坐标类型, Absolute为绝对坐标, Relative为相对坐标"
    )
    x: Optional[int] = Field(0, description="X坐标, 默认0")
    y: Optional[int] = Field(0, description="Y坐标, 默认0")


LogLevelLiteral = Literal["LOG", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Action(BaseModel):
    type: Literal[
        "LClick",
        "RClick",
        "DoubleClick",
        "TextInput",
        "KeyboardInput",
        "Delay",
        "Paste",
        "Log",
    ] = Field(
        ...,
        description="动作类型, 可选: LClick(左键点击), RClick(右键点击), DoubleClick(双击), TextInput(文本输入), KeyboardInput(键盘输入), Delay(延时), Paste(粘贴)",
    )
    position: Optional[Position] = Field(
        None, description="点击/操作位置, 部分动作类型可用"
    )
    keys: Optional[List[str]] = Field(
        list(),
        description='键盘输入的按键列表, 如["ctrl", "v"], KeyboardInput专用',
    )
    text: Optional[str] = Field(str(), description="要输入的文本, TextInput/Paste专用")
    message: Optional[str] = Field(
        str(), description="日志消息, Log专用, 用于记录操作信息"
    )
    levels: Optional[List[LogLevelLiteral]] = Field(
        list(),
        description="Log专用 日志级别, 可选: LOG, DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    duration: Optional[int] = Field(
        0, ge=0, description="操作持续时间/延时(ms), Delay专用"
    )
    use_keyboard: Optional[bool] = Field(
        False, description="是否用键盘输入(typewrite), TextInput专用"
    )


class Delay(BaseModel):
    pre: Optional[int] = Field(0, ge=0, description="前置延时(ms), 任务执行前等待时间")
    cur: Optional[int] = Field(0, ge=0, description="当前延时(ms), 任务执行中等待时间")
    post: Optional[int] = Field(0, ge=0, description="后置延时(ms), 任务执行后等待时间")


class Next(BaseModel):
    success: Optional[str] = Field(str(), description="成功时的下一个任务名")
    failure: Optional[str] = Field(str(), description="失败时的下一个任务名")


class Limits(BaseModel):
    maxCount: Optional[int] = Field(-1, ge=1, description="最大执行次数, 默认不限制")
    maxFailure: Optional[int] = Field(-1, ge=0, description="最大失败次数, 默认不限制")
    maxSuccess: Optional[int] = Field(-1, ge=0, description="最大成功次数, 默认不限制")


class Job(BaseModel):
    type: Literal["ROI", "OCR", "Input", "System", "Overload"] = Field(
        ...,
        description="任务类型, 可选: ROI(区域识别), OCR(文字识别), Input(输入操作), System(系统操作), Overload(继承)",
    )
    overload: Optional[str] = Field(
        None,
        description="继承的任务名, 仅在type为Overload时有效, 允许继承其他任务的定义",
    )
    action: Optional[Action] = Field(None, description="动作定义, 详见Action类型")
    description: Optional[str] = Field(str(), description="任务描述, 便于理解用途")
    image: Optional[Image] = Field(
        None, description="图片信息(ROI/OCR专用), 包含路径和置信度"
    )
    region: Optional[Region] = Field(
        None, description="操作区域, 指定任务作用的屏幕区域"
    )
    next: Optional[Union[str, Next]] = Field(
        None, description="下一个任务名或分支, 支持 success/failure 分支"
    )
    delay: Optional[Delay] = Field(None, description="延时设置, 控制任务前中后等待时间")
    limits: Optional[Limits] = Field(
        None, description="任务执行限制, 包含最大执行次数、失败次数等"
    )
    needs: Optional[List[str]] = Field(
        list(), description="依赖的前置任务名, 只有全部完成后才会执行本任务"
    )


class LogConfig(BaseModel):
    level: Optional[Literal["LOG", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]] = (
        Field(
            None,
            description="日志级别, 可选: LOG, DEBUG, INFO, WARNING, ERROR, CRITICAL",
        )
    )
    file: Optional[str] = Field(
        str(), description="日志文件路径, 如果为None则不写入文件"
    )
    format: Optional[str] = Field(
        "%(levelname)s - %(asctime)s - %(message)s",
        description="日志格式化字符串",
    )
    datefmt: Optional[str] = Field(
        "%Y-%m-%d %H:%M:%S.%f", description="日期时间格式化字符串"
    )
    clear: Optional[bool] = Field(False, description="是否清空日志")


class IdentifiedGlobals(BaseModel):
    debug: Optional[bool] = Field(False, description="调试模式, 开启后输出详细日志")
    colorful: Optional[bool] = Field(True, description="彩色日志输出")
    ignore: Optional[bool] = Field(False, description="忽略错误")
    logConfig: Optional[LogConfig] = Field(None, description="日志配置")


Globals = Union[IdentifiedGlobals, Dict[str, Any]]


class Workflow(BaseModel):
    begin: str = Field(..., description="起始任务名, 必须是 jobs 中的一个 key")
    globals: Optional[Globals] = Field(None, description="全局配置, 影响所有任务")
    jobs: Dict[str, Job] = Field(
        ..., description="所有任务节点, key为任务名, value为Job定义"
    )
