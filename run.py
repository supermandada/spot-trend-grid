# -*- coding: utf-8 -*-
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.BinanceAPI import BinanceAPI
from app.authorization import api_key, api_secret
from data.runBetData import RunBetData
from app.dingding import Message
from data.calcIndex import CalcIndex

binan = BinanceAPI(api_key, api_secret)
runbet = RunBetData()
msg = Message()
index = CalcIndex()


class RunMain:
    def __init__(self):
        self.coinList = runbet.get_coinList()

    async def pre_data(self, cointype):
        """获取交易对的基础信息（异步版）"""
        loop = asyncio.get_event_loop()
        grid_buy_price = await loop.run_in_executor(None, runbet.get_buy_price, cointype)
        grid_sell_price = await loop.run_in_executor(None, runbet.get_sell_price, cointype)
        quantity = await loop.run_in_executor(None, runbet.get_quantity, cointype)
        step = await loop.run_in_executor(None, runbet.get_step, cointype)
        cur_market_price = await loop.run_in_executor(None, binan.get_ticker_price, cointype)
        right_size = len(str(cur_market_price).split(".")[1])
        return [grid_buy_price, grid_sell_price, quantity, step, cur_market_price, right_size]

    async def run_for_coin(self, coinType):
        """处理单个交易对的逻辑（异步版）"""
        while True:
            try:
                data = await self.pre_data(coinType)
                grid_buy_price, grid_sell_price, quantity, step, cur_market_price, right_size = data

                if grid_buy_price >= cur_market_price:
                    res = await asyncio.get_event_loop().run_in_executor(None, msg.buy_market_msg, coinType, quantity)
                    if 'orderId' in res:  # 挂单成功
                        success_price = float(res['fills'][0]['price'])
                        await asyncio.get_event_loop().run_in_executor(None, runbet.set_ratio, coinType)
                        await asyncio.sleep(1)
                        await asyncio.get_event_loop().run_in_executor(None, runbet.set_record_price, coinType, success_price)
                        await asyncio.sleep(1)
                        await asyncio.get_event_loop().run_in_executor(None, runbet.modify_price, coinType, cur_market_price, step + 1, cur_market_price)
                        await asyncio.sleep(60)  # 挂单后暂停 1 分钟
                    else:
                        break
                elif grid_sell_price < cur_market_price:
                    if step == 0:  # 防止踏空，跟随价格上涨
                        await asyncio.get_event_loop().run_in_executor(None, runbet.modify_price, coinType, grid_sell_price, step, cur_market_price)
                    else:
                        last_price = await asyncio.get_event_loop().run_in_executor(None, runbet.get_record_price, coinType)
                        sell_amount = await asyncio.get_event_loop().run_in_executor(None, runbet.get_quantity, coinType, False)
                        porfit_usdt = (cur_market_price - last_price) * sell_amount
                        res = await asyncio.get_event_loop().run_in_executor(None, msg.sell_market_msg, coinType, sell_amount, porfit_usdt)
                        if 'orderId' in res:  # 挂单成功
                            await asyncio.get_event_loop().run_in_executor(None, runbet.set_ratio, coinType)
                            await asyncio.sleep(1)
                            await asyncio.get_event_loop().run_in_executor(None, runbet.modify_price, coinType, last_price, step - 1, cur_market_price)
                            await asyncio.sleep(1)
                            await asyncio.get_event_loop().run_in_executor(None, runbet.remove_record_price, coinType)
                            await asyncio.sleep(60)  # 挂单后暂停 1 分钟
                        else:
                            break
                else:
                    print(f"币种:{coinType} 当前市价:{cur_market_price}。未满足交易条件，继续运行。")
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"币种: {coinType}, 异常: {e}")
                break

    async def loop_run(self):
        """多线程异步运行"""
        with ThreadPoolExecutor(max_workers=3) as executor:  # 最多运行 3 个线程
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(executor, self.run_for_coin, coin) for coin in self.coinList]
            await asyncio.gather(*tasks)


if __name__ == "__main__":
    instance = RunMain()
    try:
        asyncio.run(instance.loop_run())
    except Exception as e:
        error_info = "报警：做多网格，服务停止"
        msg.dingding_warn(error_info)
        print(f"程序异常停止: {e}")
