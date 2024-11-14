from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from settings import settings
from sqlalchemy.exc import OperationalError
from db_base import Base


# <username>:password@<host>:<port>/<database_name>
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{settings.DATABASE_USERNAME}:{settings.DATABASE_PASSWORD}@"
    f"{settings.DATABASE_HOSTNAME}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,  # Adjust this number based on your expected load
    max_overflow=10,  # Allow some overflow in case of high demand
    pool_recycle=1800,  # Recycle connections every 30 minutes
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)




def get_db():
    db = SessionLocal()
    try:
        yield db
    except OperationalError as e:
        db.rollback()
        raise e
    finally:
        db.close()
