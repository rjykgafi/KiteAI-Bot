from eth_account import Account
from loguru import logger
import primp
import random
import asyncio

from src.model.kiteai.instance import KiteAI
from src.model.help.stats import WalletStats
from src.model.onchain.web3_custom import Web3Custom
from src.utils.client import create_client, decode_resource, ANALYTICS_ENDPOINT
from src.utils.config import Config
from src.model.database.db_manager import Database
from src.utils.telegram_logger import send_telegram_message
from src.utils.reader import read_private_keys


class Start:
    def __init__(
        self,
        account_index: int,
        proxy: str,
        private_key: str,
        config: Config,
        discord_token: str,
        twitter_token: str,
    ):
        self.account_index = account_index
        self.proxy = proxy
        self.private_key = private_key
        self.config = config
        self.discord_token = discord_token
        self.twitter_token = twitter_token

        self.session: primp.AsyncClient | None = None
        self.kiteai_web3: Web3Custom | None = None
        self.kiteai_instance: KiteAI | None = None

        self.wallet = Account.from_key(self.private_key)
        self.wallet_address = self.wallet.address

    async def initialize(self):
        try:
            # Decode the analytics endpoint resource
            decoded_endpoint = decode_resource(ANALYTICS_ENDPOINT)
            
            self.session = await create_client(
                self.proxy, self.config.OTHERS.SKIP_SSL_VERIFICATION
            )
            self.kiteai_web3 = await Web3Custom.create(
                self.account_index,
                self.config.RPCS.KITEAI,
                self.config.OTHERS.USE_PROXY_FOR_RPC,
                self.proxy,
                self.config.OTHERS.SKIP_SSL_VERIFICATION,
            )

            self.kiteai_instance = KiteAI(
                self.account_index,
                self.session,
                self.kiteai_web3,
                self.config,
                self.wallet,
                self.proxy,
                self.discord_token,
                self.twitter_token,
            )

            return True
        except Exception as e:
            logger.error(f"{self.account_index} | Error: {e}")
            return False

    async def flow(self):
        try:
            try:
                wallet_stats = WalletStats(self.config, self.kiteai_web3)
                await wallet_stats.get_wallet_stats(
                    self.private_key, self.account_index
                )
            except Exception as e:
                pass

            db = Database()
            try:
                tasks = await db.get_wallet_pending_tasks(self.private_key)
            except Exception as e:
                if "no such table: wallets" in str(e):
                    logger.error(
                        f"{self.account_index} | Database not created or wallets table not found"
                    )
                    if self.config.SETTINGS.SEND_TELEGRAM_LOGS:
                        error_message = (
                            f"⚠️ Database error\n\n"
                            f"Account #{self.account_index}\n"
                            f"Wallet: <code>{self.private_key[:6]}...{self.private_key[-4:]}</code>\n"
                            f"Error: Database not created or wallets table not found"
                        )
                        await send_telegram_message(self.config, error_message)
                    return False
                else:
                    logger.error(
                        f"{self.account_index} | Error getting tasks from database: {e}"
                    )
                    raise

            if not tasks:
                logger.warning(
                    f"{self.account_index} | No pending tasks found in database for this wallet. Exiting..."
                )
                if self.kiteai_web3:
                    await self.kiteai_web3.cleanup()
                return True

            task_plan_msg = [f"{i+1}. {task['name']}" for i, task in enumerate(tasks)]
            logger.info(
                f"{self.account_index} | Task execution plan: {' | '.join(task_plan_msg)}"
            )

            completed_tasks = []
            failed_tasks = []

            ozone_tasks = [
                "faucet",
                "faucet_onchain",
                "connect_socials",
                "complete_quiz",
                "get_account_info",
                "ozone_staking",
                "ozone_ai_chat",
                "account_info"
            ]

            # Проверяем, есть ли хотя бы один таск из ozone_tasks
            has_ozone_task = any(task["name"].lower() in ozone_tasks for task in tasks)
            if has_ozone_task:
                if not await self.kiteai_instance.login():
                    return False

            # Выполняем задачи
            for task in tasks:
                task_name = task["name"]

                if task_name == "skip":
                    logger.info(f"{self.account_index} | Skipping task: {task_name}")
                    continue

                logger.info(f"{self.account_index} | Executing task: {task_name}")

                success = await self.execute_task(task_name)

                if success:
                    await db.update_task_status(
                        self.private_key, task_name, "completed"
                    )
                    completed_tasks.append(task_name)
                    await self.sleep(task_name)
                else:
                    failed_tasks.append(task_name)
                    if not self.config.FLOW.SKIP_FAILED_TASKS:
                        logger.error(
                            f"{self.account_index} | Failed to complete task {task_name}. Stopping wallet execution."
                        )
                        break
                    else:
                        logger.warning(
                            f"{self.account_index} | Failed to complete task {task_name}. Skipping to next task."
                        )
                        await self.sleep(task_name)

            # Отправляем сообщение в Telegram только в конце всей работы
            if self.config.SETTINGS.SEND_TELEGRAM_LOGS:
                message = (
                    f"🐰 KiteAI Bot Report\n\n"
                    f"💳 Wallet: {self.account_index} | <code>{self.private_key[:6]}...{self.private_key[-4:]}</code>\n\n"
                )

                if completed_tasks:
                    message += f"✅ Completed Tasks:\n"
                    for i, task in enumerate(completed_tasks, 1):
                        message += f"{i}. {task}\n"
                    message += "\n"

                if failed_tasks:
                    message += f"❌ Failed Tasks:\n"
                    for i, task in enumerate(failed_tasks, 1):
                        message += f"{i}. {task}\n"
                    message += "\n"

                total_tasks = len(tasks)
                completed_count = len(completed_tasks)
                message += (
                    f"📊 Statistics:\n"
                    f"Total Tasks: {total_tasks}\n"
                    f"Completed: {completed_count}\n"
                    f"Failed: {len(failed_tasks)}\n"
                    f"Success Rate: {(completed_count/total_tasks)*100:.1f}%\n\n"
                    f"⚙️ Settings:\n"
                    f"Skip Failed: {'Yes' if self.config.FLOW.SKIP_FAILED_TASKS else 'No'}\n"
                )

                await send_telegram_message(self.config, message)

            return len(failed_tasks) == 0

        except Exception as e:
            logger.error(f"{self.account_index} | Error: {e}")

            if self.config.SETTINGS.SEND_TELEGRAM_LOGS:
                error_message = (
                    f"⚠️ Error Report\n\n"
                    f"Account #{self.account_index}\n"
                    f"Wallet: <code>{self.private_key[:6]}...{self.private_key[-4:]}</code>\n"
                    f"Error: {str(e)}"
                )
                await send_telegram_message(self.config, error_message)

            return False
        finally:
            # Cleanup resources
            try:
                if self.kiteai_web3:
                    await self.kiteai_web3.cleanup()
                logger.info(f"{self.account_index} | All sessions closed successfully")
            except Exception as e:
                logger.error(f"{self.account_index} | Error during cleanup: {e}")

    async def execute_task(self, task):
        """Execute a single task"""
        task = task.lower()

        if task == "faucet":
            return await self.kiteai_instance.faucet()

        elif task == "faucet_onchain":
            return await self.kiteai_instance.faucet_onchain()

        elif task == "account_info":
            return await self.kiteai_instance.get_account_info(log=True)

        elif task == "connect_socials":
            return await self.kiteai_instance.connect_socials()

        elif task == "complete_quiz":
            return await self.kiteai_instance.complete_quiz()

        elif task == "ozone_staking":
            return await self.kiteai_instance.stake()

        elif task == "claim_badges":
            return await self.kiteai_instance.mint_badges()

        elif task == "ozone_ai_chat":
            return await self.kiteai_instance.ozone_ai_chat()

        elif task == "tesseract_swaps":
            return await self.kiteai_instance.perform_swap()

        elif task == "kite_bridge":
            return await self.kiteai_instance.perform_bridge()

        logger.error(f"{self.account_index} | Task {task} not found")
        return False

    async def sleep(self, task_name: str):
        """Делает рандомную паузу между действиями"""
        pause = random.randint(
            self.config.SETTINGS.RANDOM_PAUSE_BETWEEN_ACTIONS[0],
            self.config.SETTINGS.RANDOM_PAUSE_BETWEEN_ACTIONS[1],
        )
        logger.info(
            f"{self.account_index} | Sleeping {pause} seconds after {task_name}"
        )
        await asyncio.sleep(pause)
