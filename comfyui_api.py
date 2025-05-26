import random
import os
import json
import urllib.request
import urllib.parse
from astrbot.api import logger
import aiohttp
import websockets

# 获取当前文件的绝对路径
current_file_path = os.path.abspath(__file__)
# 获取当前文件所在目录的绝对路径
current_directory = os.path.dirname(current_file_path)
# comfyui工作流文件所在目录
workflow_file_path = os.path.join(current_directory, 'workflow', 'workflow_api.json')

workflow_file_path_safe = os.path.join(current_directory, 'workflow', 'workflow_api_safe.json')


class ComfyUI:
    def __init__(self, config: dict, client_id) -> None:
        self.client_id = client_id
        self.server_address = config.get("server_address")
        self.steps = config.get("sub_config").get("steps")
        self.width = config.get("sub_config").get("width")
        self.height = config.get("sub_config").get("height")
        self.negative_prompt = config.get("sub_config").get("negative_prompt")
        self.ws = None
        self._initialized = False
        
    async def init_async(self):
        if self._initialized:
            return
        ws_url = f"ws://{self.server_address}/ws?clientId={self.client_id}"
        #  关闭代理
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"

        # 最大帧大小：10MB 禁用内部队列限制
        self.ws = await websockets.connect(ws_url,ping_interval=None,max_size=10 * 1024 * 1024, max_queue=None  )
        await self.ws.ping()
        self._initialized = True
        print("✅ WebSocket 已连接")
    # 生成绘图任务
    def queue_prompt(self, prompt):
        p = {"prompt": prompt, "client_id": self.client_id}
        data = json.dumps(p).encode('utf-8')
        req = urllib.request.Request("http://{}/prompt".format(self.server_address), data=data)
        return json.loads(urllib.request.urlopen(req).read())

    async def a_queue_prompt(self, prompt):
        url = f"http://{self.server_address}/prompt"
        payload = {
            "prompt": prompt,
            "client_id": self.client_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()  # 如果服务器返回错误码会抛出异常
                return await response.json()
    # 预览图片
    def get_image(self, filename, subfolder, folder_type):
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url_values = urllib.parse.urlencode(data)
        with urllib.request.urlopen("http://{}/view?{}".format(self.server_address, url_values)) as response:
            return response.read()

    # 获取历史生成的图片
    def get_history(self, prompt_id):
        with urllib.request.urlopen("http://{}/history/{}".format(self.server_address, prompt_id)) as response:
            return json.loads(response.read())

    # 通过与ComfyUI建立的WebSocket连接中，实时获取绘图任务中的数据（当前正在执行哪个节点执行 以及 最终生成的图片）
    async def get_images(self, prompt):
        # prompt_id = self.queue_prompt(prompt)['prompt_id']
        # 异步执行
        resp = await self.a_queue_prompt(prompt)
        prompt_id = resp['prompt_id']
        logger.info(f"创建任务完成，prompt_id:{prompt_id}")
        output_images = {}
        current_node = ""
        while True:
            out = await self.ws.recv()
            # 从打印日志中可以实时记录节点的执行过程以及生成的图片进度
            # print(f"out:{out}")
            if out is None:
                # 如果 out 为 None，决定如何处理
                logger.info("接收到 None 数据，结束接收")
                break

            if isinstance(out, str):
                
                message = json.loads(out)
                # logger.info(f"接收到数据,进行处理:{message}")
                if message['type'] == 'executing':
                    data = message['data']
                    if data['prompt_id'] == prompt_id:
                        if data['node'] is None:
                            break  # Execution is done
                        else:
                            current_node = data['node']
                            logger.info(f"正在执行节点：{current_node}")
            else:
                # logger.info(f"接收到非str数据,进行处理")
                # logger.info(f"正在执行节点：{current_node}")
                if current_node == '36':
                    logger.info(f"图片生成完成，开始保存：{current_node}")
                    images_output = output_images.get(current_node, [])
                    images_output.append(out[8:])
                    output_images[current_node] = images_output

        return output_images

    # 封装文生图调用入口，prompt: 正向提示词
    async def text_2_img(self, prompt, img_width, img_height,safe=False):
        if img_width is None:
            img_width = self.width
        if img_height is None:
            img_height = self.height

        # 加载ComfyUI工作流的json文件
        with open(workflow_file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        if safe:
            with open(workflow_file_path_safe, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        
        # 生成15位的随机种子
        random_number = ''.join(random.choices('123456789', k=15))
        # 将提示词和随机种子加入到最终的工作流json中
        json_data["32"]["inputs"]["text"] = prompt
        # json_data["27"]["inputs"]["width"] = img_width
        # json_data["27"]["inputs"]["height"] = img_height
        # json_data["31"]["inputs"]["steps"] = self.steps
        json_data["4"]["inputs"]["seed"] = random_number
        json_data["20"]["inputs"]["seed"] = random_number
        # json_data["33"]["inputs"]["text"] = self.negative_prompt
        logger.info(f"seed:{random_number},steps:{self.steps},width:{img_width},height:{img_height}")
        logger.info(f"Negative Prompt:{self.negative_prompt}")
        # 调用以上 get_images 方法生成图片
        logger.info(f"已加载json:{json_data}")
        images =await self.get_images(json_data)

        for node_id in images:
            for image_data in images[node_id]:
                return image_data
