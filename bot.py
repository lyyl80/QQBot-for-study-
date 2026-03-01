import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 导入apscheduler插件以确保调度器可用
import nonebot_plugin_apscheduler

nonebot.load_plugins("src/plugins")

if __name__ == "__main__":
    nonebot.run()
