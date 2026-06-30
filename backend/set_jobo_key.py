import asyncio
from database import SessionLocal, Setting
from sqlalchemy import select

async def run():
    api_key = "jbe_live_dHsv8OABhAt5bDAt0f8Vz_HnmxU1mG5thcZbz2u8WH9ovWaFApEKpeA9opxU0srXE"
    
    async with SessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == "jobo_api_key"))
        setting = result.scalar_one_or_none()
        
        if setting:
            setting.value = api_key
        else:
            setting = Setting(key="jobo_api_key", value=api_key)
            db.add(setting)
            
        await db.commit()
        print("Successfully saved Jobo API Key to DB.")

if __name__ == "__main__":
    asyncio.run(run())
