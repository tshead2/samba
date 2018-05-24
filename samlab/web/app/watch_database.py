# Copyright 2018, National Technology & Engineering Solutions of Sandia, LLC
# (NTESS).  Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import logging
import pprint
import threading

# Setup logging.
log = logging.getLogger(__name__)

# Get the web server.
from samlab.web.app import application, socketio

# Get the database.
from samlab.web.app.database import database, fs


def watch_objects(otype):
    for change in database[otype].watch():
        operation = change["operationType"]
        oid = change["documentKey"]["_id"]

        if operation == "insert":
            socketio.emit("object-created", {"otype": otype, "oid": oid})
        elif operation == "update":
            socketio.emit("object-changed", {"otype": otype, "oid": oid})
        elif operation == "delete":
            socketio.emit("object-deleted", {"otype": otype, "oid": oid})


threading.Thread(target=watch_objects, args=("observations",), daemon=True).start()
threading.Thread(target=watch_objects, args=("trials",), daemon=True).start()
threading.Thread(target=watch_objects, args=("models",), daemon=True).start()
threading.Thread(target=watch_objects, args=("deliveries",), daemon=True).start()
threading.Thread(target=watch_objects, args=("favorites",), daemon=True).start()

