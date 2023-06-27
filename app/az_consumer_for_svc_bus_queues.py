import json
import logging
import datetime
import time
import os
import random
import uuid
import socket

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.eventhub import EventHubProducerClient
from azure.eventhub import EventData
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient

# ANSI color codes
GREEN_COLOR = "\033[32m"
RED_COLOR = "\033[31m"
RESET_COLOR = "\033[0m"

# Example usage with logging
logging.info(f'{GREEN_COLOR}This is green text{RESET_COLOR}')


class GlobalArgs:
    OWNER = "Mystique"
    VERSION = "2023-06-27"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    EVNT_WEIGHTS = {"success": 80, "fail": 20}
    TRIGGER_RANDOM_FAILURES = os.getenv("TRIGGER_RANDOM_FAILURES", True)
    WAIT_SECS_BETWEEN_MSGS = int(os.getenv("WAIT_SECS_BETWEEN_MSGS", 2))
    TOT_MSGS_TO_PRODUCE = int(os.getenv("TOT_MSGS_TO_PRODUCE", 10))

    SVC_BUS_CONNECTION_STR = os.getenv("SVC_BUS_CONNECTION_STR")
    SVC_BUS_FQDN = os.getenv(
        "SVC_BUS_FQDN", "warehouse-q-svc-bus-ns-002.servicebus.windows.net")
    SVC_BUS_Q_NAME = os.getenv("SVC_BUS_Q_NAME", "warehouse-q-svc-bus-q-002")
    SVC_BUS_TOPIC_NAME = os.getenv(
        "SVC_BUS_TOPIC_NAME", "warehouse-ne-topic-002")

    EVENT_HUB_FQDN = os.getenv(
        "EVENT_HUB_FQDN", "warehouse-event-hub-ns-event-hub-streams-002.servicebus.windows.net")
    EVENT_HUB_NAME = os.getenv("EVENT_HUB_NAME", "store-events-stream-002")

    SA_NAME = os.getenv("SA_NAME", "warehousehuscgs003")
    BLOB_SVC_ACCOUNT_URL = os.getenv(
        "BLOB_SVC_ACCOUNT_URL", "https://warehousehuscgs003.blob.core.windows.net")
    BLOB_NAME = os.getenv("BLOB_NAME", "store-events-blob-003")
    BLOB_PREFIX = "store_events/raw"

    COSMOS_DB_URL = os.getenv(
        "COSMOS_DB_URL", "https://partition-processor-db-account-003.documents.azure.com:443/")
    COSMOS_DB_NAME = os.getenv(
        "COSMOS_DB_NAME", "partition-processor-db-account-003")
    COSMOS_DB_CONTAINER_NAME = os.getenv(
        "COSMOS_DB_CONTAINER_NAME", "store-backend-container-003")

    SVC_BUS_FQDN = os.getenv(
        "SVC_BUS_FQDN", "warehouse-q-svc-bus-ns-002.servicebus.windows.net")
    SVC_BUS_Q_NAME = os.getenv("SVC_BUS_Q_NAME", "warehouse-q-svc-bus-q-002")
    SVC_BUS_TOPIC_NAME = os.getenv(
        "SVC_BUS_TOPIC_NAME", "warehouse-q-svc-bus-q-002")

    EVENT_HUB_FQDN = os.getenv(
        "EVENT_HUB_FQDN", "warehouse-event-hub-ns-partition-processor-003.servicebus.windows.net")
    EVENT_HUB_NAME = os.getenv("EVENT_HUB_NAME", "store-events-stream-003")
    EVENT_HUB_SALE_EVENTS_CONSUMER_GROUP_NAME = os.getenv(
        "EVENT_HUB_SALE_EVENTS_CONSUMER_GROUP_NAME", "sale-events-consumers-003")


def _rand_coin_flip():
    r = False
    if GlobalArgs.TRIGGER_RANDOM_FAILURES:
        r = random.choices([True, False], weights=[0.1, 0.9], k=1)[0]
    return r


def _gen_uuid():
    return str(uuid.uuid4())


def generate_event():

    # Following Patterns are implemented
    # If event_type is inventory_event, then is_return is True for 50% of the events
    # 10% of total events are poison pill events, bad_msg attribute is True and store_id is removed
    # Event attributes are set with priority_shipping, is_return, and event type

    _categories = ["Books", "Games", "Mobiles", "Groceries", "Shoes", "Stationaries", "Laptops", "Tablets",
                   "Notebooks", "Camera", "Printers", "Monitors", "Speakers", "Projectors", "Cables", "Furniture"]
    _variants = ["black", "red"]
    _evnt_types = ["sale_event", "inventory_event"]
    _currencies = ["USD", "INR", "EUR", "GBP",
                   "AUD", "CAD", "SGD", "JPY", "CNY", "HKD"]
    _payments = ["credit_card", "debit_card", "cash",
                 "wallet", "upi", "net_banking", "cod", "gift_card"]

    _qty = random.randint(1, 99)
    _s = round(random.random() * 100, 2)

    _evnt_type = random.choices(_evnt_types, weights=[0.8, 0.2], k=1)[0]
    _u = _gen_uuid()
    p_s = random.choices([True, False], weights=[0.3, 0.7], k=1)[0]
    is_return = False

    if _evnt_type == "inventory_event":
        is_return = bool(random.getrandbits(1))

    evnt_body = {
        "id": _u,
        "event_type": _evnt_type,
        "store_id": random.randint(1, 10),
        "store_fqdn": str(socket.getfqdn()),
        "store_ip": str(socket.gethostbyname(socket.gethostname())),
        "cust_id": random.randint(100, 999),
        "category": random.choice(_categories),
        "sku": random.randint(18981, 189281),
        "price": _s,
        "qty": _qty,
        "currency": random.choice(_currencies),
        "discount": random.randint(0, 75),
        "gift_wrap": random.choices([True, False], weights=[0.3, 0.7], k=1)[0],
        "variant": random.choice(_variants),
        "priority_shipping": p_s,
        "payment_method": random.choice(_payments),
        "ts": datetime.datetime.now().isoformat(),
        "contact_me": "github.com/miztiik",
        "is_return": is_return
    }

    if _rand_coin_flip():
        evnt_body.pop("store_id", None)
        evnt_body["bad_msg"] = True

    _attr = {
        "event_type": _evnt_type,
        "priority_shipping": str(p_s),
        "is_return": str(is_return)
    }

    return evnt_body, _attr


def evnt_producer():
    resp = {
        "status": False,
        "tot_msgs": 0,
        "event_sample": None
    }

    try:
        t_msgs = 0
        p_cnt = 0
        s_evnts = 0
        inventory_evnts = 0
        t_sales = 0

        # Start timing the event generation
        event_gen_start_time = time.time()

        # Initialize Azure Auth Token & Clients
        azure_log_level = logging.getLogger("azure").setLevel(logging.ERROR)
        default_credential = DefaultAzureCredential(
            logging_enable=False, logging=azure_log_level)

        blob_svc_client = BlobServiceClient(
            GlobalArgs.BLOB_SVC_ACCOUNT_URL, credential=default_credential, logging=azure_log_level)

        cosmos_client = CosmosClient(
            url=GlobalArgs.COSMOS_DB_URL, credential=default_credential)
        db_client = cosmos_client.get_database_client(
            GlobalArgs.COSMOS_DB_NAME)
        db_container = db_client.get_container_client(
            GlobalArgs.COSMOS_DB_CONTAINER_NAME)

        while t_msgs < GlobalArgs.TOT_MSGS_TO_PRODUCE:
            evnt_body, evnt_attr = generate_event()
            t_msgs += 1
            t_sales += evnt_body["price"] * evnt_body["qty"]

            if evnt_body.get("bad_msg"):
                p_cnt += 1

            if evnt_attr["event_type"] == "sale_event":
                s_evnts += 1
            elif evnt_attr["event_type"] == "inventory_event":
                inventory_evnts += 1

            if t_msgs == 1:
                resp["event_sample"] = evnt_body

            time.sleep(GlobalArgs.WAIT_SECS_BETWEEN_MSGS)
            logging.info(f"generated_event:{json.dumps(evnt_body)}")

            # write to blob
            _evnt_type = evnt_attr["event_type"]
            write_to_blob(_evnt_type, evnt_body, blob_svc_client)

            # # Ingest to CosmosDB
            # doc.set(func.Document.from_json(json.dumps(evnt_body)))
            # logging.info('Document injestion success')

            # Write To Service Bus Queue
            # write_to_svc_bus_q(evnt_body, evnt_attr)

            # # Write To Service Bus Topic
            # write_to_svc_bus_topic(evnt_body, evnt_attr)

            # Write To Service Bus Topic
            # write_to_event_hub(evnt_body, evnt_attr)

            # write to cosmosdb
            write_to_cosmosdb(evnt_body, db_container)

        event_gen_end_time = time.time()  # Stop timing the event generation
        event_gen_duration = event_gen_end_time - \
            event_gen_start_time  # Calculate the duration

        resp["event_gen_duration"] = event_gen_duration
        resp["tot_msgs"] = t_msgs
        resp["bad_msgs"] = p_cnt
        resp["sale_evnts"] = s_evnts
        resp["inventory_evnts"] = inventory_evnts
        resp["tot_sales"] = t_sales
        resp["status"] = True

    except Exception as e:
        logging.error(f"ERROR: {type(e).__name__}: {str(e)}")
        resp["err_msg"] = f"ERROR: {type(e).__name__}: {str(e)}"

    return resp


def write_to_blob(container_prefix: str, data: dict, blob_svc_client):
    try:
        blob_name = f"{GlobalArgs.BLOB_PREFIX}/event_type={container_prefix}/dt={datetime.datetime.now().strftime('%Y_%m_%d')}/{datetime.datetime.now().strftime('%s%f')}.json"
        if container_prefix is None:
            blob_name = f"{GlobalArgs.BLOB_PREFIX}/dt={datetime.datetime.now().strftime('%Y_%m_%d')}/{datetime.datetime.now().strftime('%s%f')}.json"

        blob_client = blob_svc_client.get_blob_client(
            container=GlobalArgs.BLOB_NAME, blob=blob_name)

        if blob_client.exists():
            blob_client.delete_blob()
            logging.debug(
                f"Blob {blob_name} already exists. Deleted the file.")

        resp = blob_client.upload_blob(json.dumps(data).encode("UTF-8"))
        logging.info(
            f"Blob {GREEN_COLOR}{blob_name}{RESET_COLOR} uploaded successfully")
        logging.debug(f"{resp}")
    except Exception as e:
        logging.exception(f"ERROR:{str(e)}")


def write_to_cosmosdb(data: dict, db_container):
    try:
        resp = db_container.create_item(body=data)
        logging.info(
            f"Document with id {GREEN_COLOR}{data['id']}{RESET_COLOR} written to CosmosDB successfully")
        logging.debug(f"{resp}")
    except Exception as e:
        logging.exception(f"ERROR:{str(e)}")


def main(msg: func.ServiceBusMessage) -> str:
    _a_resp = {
        "status": False,
        "miztiik_event_processed": False,
        "last_processed_on": None
    }
    msg_body = msg.get_body().decode("utf-8")
    try:

        result = json.dumps({
            'message_id': msg.message_id,
            'body': msg.get_body().decode('utf-8'),
            'content_type': msg.content_type,
            'delivery_count': msg.delivery_count,
            'expiration_time': (msg.expiration_time.isoformat() if
                                msg.expiration_time else None),
            'label': msg.label,
            'partition_key': msg.partition_key,
            'reply_to': msg.reply_to,
            'reply_to_session_id': msg.reply_to_session_id,
            'scheduled_enqueue_time': (msg.scheduled_enqueue_time.isoformat() if
                                       msg.scheduled_enqueue_time else None),
            'session_id': msg.session_id,
            'time_to_live': msg.time_to_live,
            'to': msg.to,
            'user_properties': msg.user_properties,
            'event_type': msg.user_properties.get('event_type')
        })

        logging.info(f"{json.dumps(msg_body, indent=4)}")
        logging.info(f"recv_msg: {result}")

        azure_log_level = logging.getLogger("azure").setLevel(logging.ERROR)
        default_credential = DefaultAzureCredential(
            logging_enable=False, logging=azure_log_level)

        blob_svc_client = BlobServiceClient(
            GlobalArgs.BLOB_SVC_ACCOUNT_URL, credential=default_credential, logging=azure_log_level)

        cosmos_client = CosmosClient(
            url=GlobalArgs.COSMOS_DB_URL, credential=default_credential)
        db_client = cosmos_client.get_database_client(
            GlobalArgs.COSMOS_DB_NAME)
        db_container = db_client.get_container_client(
            GlobalArgs.COSMOS_DB_CONTAINER_NAME)

        # write to blob
        _evnt_type = msg.user_properties.get("event_type")
        write_to_blob(_evnt_type, json.loads(msg_body), blob_svc_client)

        # write to cosmosdb
        # write_to_cosmosdb(json.loads(msg_body), db_container)
        _a_resp["status"] = True
        _a_resp["miztiik_event_processed"] = True
        _a_resp["last_processed_on"] = datetime.datetime.now().isoformat()
        logging.info(f"{GREEN_COLOR} {json.dumps(_a_resp)} {RESET_COLOR}")

    except Exception as e:
        logging.exception(f"ERROR:{str(e)}")

    logging.info(json.dumps(_a_resp, indent=4))
