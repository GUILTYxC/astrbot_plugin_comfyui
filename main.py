import uuid
import asyncio
import os
import random
import json
from dataclasses import asdict
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import *
from astrbot.api import logger
from .comfyui_api import ComfyUI
from .oss import upload_public_file
from . import platform_type_constants
from astrbot.core.message.message_event_result import MessageChain

# 有队列机制的版本

# 获取当前文件的绝对路径
current_file_path = os.path.abspath(__file__)
# 获取当前文件所在目录的绝对路径
current_directory = os.path.dirname(current_file_path)
# 图片生成存放目录
img_path = os.path.join(current_directory, 'output', 'temp.png')

@register("astrbot_plugin_comfyui", "guilty", "调用ComfyUI 服务进行文生图", "1.0.0",
          "https://github.com/GUILTYxC/astrbot_plugin_comfyui")
class ComfyUIPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.task_queue = asyncio.Queue()
        self.worker_started = False

        client_id = str(uuid.uuid4())
        try:
            self.comfy_ui = ComfyUI(config, client_id)
        except Exception:
            logger.error(f"【初始化 ComfyUI Websocket 客户端失败，请注意是否已开启 ComfyUI 服务端】")

    async def init_async(self):
        if not self.worker_started:
            asyncio.create_task(self.worker())
            self.worker_started = True
        await self.comfy_ui.init_async()

    async def worker(self):
        logger.info("Worker 启动，等待任务中...")
        while True:
            task = await self.task_queue.get()
            try:
                await self.handle_task(task)
            except Exception as e:
                logger.error(f"任务处理失败: {e}")
            self.task_queue.task_done()
            logger.info(f"剩余任务数量{self.task_queue.qsize()}")





    async def handle_task(self, task):
        event = task['event']
        prompt = task['prompt']
        safe = task['safe']
        user_name = task['user_name']

        start_msg = event.make_result().message(f"🎨 轮到你啦，{user_name}！正在生成图像，请稍等...")
        await event.send(start_msg)

        try:
            img = await self.comfy_ui.text_2_img(prompt, None, None, safe)

            with open(img_path, 'wb') as fp:
                fp.write(img)

            uuid_name = uuid.uuid4().hex
            upload_public_file(
                file_path=img_path,
                bucket_name="image",
                object_name="ai/" + uuid_name + ".png",
                endpoint_url="http://123.56.117.196:9000",
                access_key="admin",
                secret_key="admin123456"
            )
            file_url = f"http://123.56.117.196:9000/image/ai/{uuid_name}.png"

            platform_name = event.get_platform_name()
            if platform_name == platform_type_constants.DingDing:
                img_result = event.image_result(file_url)
                # chain_msg = Image.fromURL(file_url)
            else:
                img_result = event.image_result(img_path)
                # chain_msg = Image.fromFileSystem(img_path)

            logger.info(f"将图片 {file_url} 发送给用户...")
            # await event.send_chain([chain_msg])
            await event.send(img_result)
            logger.info(f"图片 {file_url} 发送成功！")

        except Exception as e:
            # 发送异常消息
            err_msg = event.make_result().message(f"❌ 生成图像失败：{str(e)}")
            await event.send(err_msg)


    @filter.command("draw", alias={'约稿'})
    async def comfyui_txt2img(self, event: AstrMessageEvent, prompt: str) -> MessageEventResult:
        await self.init_async()  # ← 确保初始化 WebSocket 和启动 worker

        user_name = event.get_sender_name() if event.get_sender_name() else event.get_sender_id()
        platform_name = event.get_platform_name()
        safe = platform_name == platform_type_constants.QQ

        prompt = event.get_message_str().replace("draw", "", 1).replace("约稿", "", 1)
        prompt += ',masterpiece, best quality, highly detailed'
        if safe:
            prompt = 'General, ' + prompt

        logger.info(f"prompt:{prompt}")

        position = self.task_queue.qsize() + 1
        yield event.plain_result(f"🎨 {user_name}，你的画图请求已加入队列，当前排队位置：{position}，请稍候...")
        logger.info("向队列中加入任务")
        await self.task_queue.put({
            "event": event,
            "prompt": prompt,
            "safe": safe,
            "user_name": user_name
        })
        logger.info(f"队列已添加任务，当前任务数量为{self.task_queue.qsize()}")

        return

    @filter.command("eugeo", alias={'测试'})
    async def eugeo(self, event: AstrMessageEvent, prompt: str) -> MessageEventResult:
        logger.info(f"收到用户请求：平台：{event.get_platform_name()}")
        yield event.plain_result(f"收到用户请求：平台：{event.get_platform_name()}")
        yield event.plain_result(f"收到用户请求：{json.dumps(asdict(event.platform_meta))}")
