from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, JSON, event
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.config import DATA
Base = declarative_base()
engine = create_engine("sqlite:///" + str(DATA / "spill.db"), connect_args={"check_same_thread":False})
@event.listens_for(engine, "connect")
def sqlite_pragmas(connection, _):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
Session = sessionmaker(bind=engine)
def now():
    return datetime.now(timezone.utc).isoformat()

class User(Base):
    __tablename__="users"
    id=Column(Integer,primary_key=True)
    name=Column(String,nullable=False)
    email=Column(String,unique=True,nullable=False)
    password=Column(String,nullable=False)

class Repository(Base):
    __tablename__="repositories"
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=False)
    name=Column(String)
    url=Column(String)
    branch=Column(String)
    path=Column(String)
    token=Column(Text)
    commit=Column(String)
    updated_at=Column(String,default=now)
    snapshot_id=Column(Integer)
    kind=Column(String,default="github")

class Snapshot(Base):
    __tablename__="snapshots"
    id=Column(Integer,primary_key=True)
    repository_id=Column(Integer,ForeignKey("repositories.id",ondelete="CASCADE"))
    commit=Column(String)
    created_at=Column(String,default=now)
    data=Column(JSON)

class GraphNode(Base):
    __tablename__="graph_nodes"
    id=Column(Integer,primary_key=True)
    snapshot_id=Column(Integer,ForeignKey("snapshots.id",ondelete="CASCADE"))
    path=Column(String)
    features=Column(JSON)

class GraphEdge(Base):
    __tablename__="graph_edges"
    id=Column(Integer,primary_key=True)
    snapshot_id=Column(Integer,ForeignKey("snapshots.id",ondelete="CASCADE"))
    source=Column(String)
    target=Column(String)
    kind=Column(String)

class Analysis(Base):
    __tablename__="analyses"
    id=Column(Integer,primary_key=True)
    repository_id=Column(Integer,ForeignKey("repositories.id",ondelete="CASCADE"))
    snapshot_id=Column(Integer,ForeignKey("snapshots.id",ondelete="CASCADE"))
    user_id=Column(Integer,ForeignKey("users.id"))
    created_at=Column(String,default=now)
    status=Column(String,default="complete")
    report=Column(JSON)

class Impact(Base):
    __tablename__="impacts"
    id=Column(Integer,primary_key=True)
    analysis_id=Column(Integer,ForeignKey("analyses.id",ondelete="CASCADE"))
    data=Column(JSON)

class ModelMetadata(Base):
    __tablename__="model_metadata"
    version=Column(String,primary_key=True)
    data=Column(JSON)

def init_db():
    Base.metadata.create_all(engine)

