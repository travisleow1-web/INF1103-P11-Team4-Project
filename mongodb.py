import os
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

#reads .env file from the current dir and injects variables onto os.environment
load_dotenv()

# Retrieve variables
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "default_db")

if not MONGO_URI:
  raise ValueError("MONGO_URI not found in environment variables.")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

class MongoDataManager:
  def __init__(self):
    client = MongoClient(MONGO_URI)
    db = client["my_application"]
    self.collection = db["records"]

  def InsertRecord(self, records):
    for record, decision in records:
      entry = {
        **record,
        "decision": decision,
        "saved_at": datetime.now().isoformat(),
        "flagged": decision["needs_human"] or decision["overall_risk"] != "Low",
        "delayed": decision["outcome"] == "DELAY",
      }
      result = self.collection.insert_one(entry)
      if result.acknowledged == True:
        print("Insertion Successful")
      else:
        print("Uh Oh Stinky")

  def DeleteRecord(self, ids):
    for id in ids:
      result = self.collection.delete_one(id)
      if result.acknowledged == True:
        print("Deletion Successful")
      else:
        print("Uh Oh Stinky")

  def FindRecord(self, query):
    """Find Record(query) will query mongodb based on a dictionary query"""
    result = list(self.collection.find(query))
    return result

  def UpdateRecord(self, id, update):
    self.collection.update_one(
      {"_id": ObjectId(id)},
      {"$set":{
        update
      }}
    )