from aios.core.engine import CoreEngine
import asyncio


async def main():
    core = CoreEngine()
    await core.start()
    print("AIOS Core Engine is READY.")
    print(core.status())

    try:
        await asyncio.Event().wait()
    finally:
        await core.shutdown()


if __name__ == "__main__":
    asyncio.run(main())