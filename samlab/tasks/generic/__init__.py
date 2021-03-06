# Copyright 2018, National Technology & Engineering Solutions of Sandia, LLC
# (NTESS).  Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import functools
import io
import logging
import os
import tempfile
import zipfile

log = logging.getLogger(__name__)

import gridfs
import huey
import numpy
import pymongo

import samlab.deserialize
import samlab.mime
import samlab.object
import samlab.observation


@functools.lru_cache(maxsize=None)
def get_database_client(uri):
    return pymongo.MongoClient(uri)


@functools.lru_cache(maxsize=None)
def get_database(uri, name):
    client = get_database_client(uri)
    database = client[name]
    fs = gridfs.GridFS(database)
    return database, fs


class Queue(object):
    def __init__(self):
        def export_observations_impl(database_uri, database_name, search):
            database, fs = get_database(database_uri, database_name)
            if search:
                observations = samlab.observation.expand(database, samlab.object.search(database, "observations", search))
            else:
                observations = list(database.observations.find({}))

            keys = numpy.unique([key for observation in observations for key in observation["content"].keys() if observation["content"][key]["content-type"] in ["image/jpeg", "image/png"]])

            directory = tempfile.mkdtemp()
            log.info("Exporting observations to %s", directory)
            zpath = os.path.join(directory, "observations.zip")
            with zipfile.ZipFile(zpath, mode="w") as zfile:
                log.info("Creating zipfile %s", zpath)

                manifest = io.StringIO()
                manifest.write("_id")
                for key in keys:
                    manifest.write(",%s" % key)
                manifest.write("\n")
                for observation in observations:
                    manifest.write("%s" % observation["_id"])
                    for key in keys:
                        if key in observation["content"]:
                            rname = "%s-%s%s" % (observation["_id"], key, samlab.mime.lookup_extension(observation["content"][key]["content-type"]))
                            content = fs.get(observation["content"][key]["data"])
                            zfile.writestr(rname, content.read())
                            manifest.write(",%s" % rname)
                        else:
                            manifest.write(", ")
                    manifest.write("\n")
                zfile.writestr("manifest.csv", manifest.getvalue())

            return {
                "directory": directory,
                "count": len(observations),
            }


        self._queue = huey.RedisHuey("samlab-generic-queue")
        self.export_observations = huey.api.TaskWrapper(self._queue, export_observations_impl)

    @property
    def queue(self):
        return self._queue

