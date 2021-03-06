# Copyright 2018, National Technology & Engineering Solutions of Sandia, LLC
# (NTESS).  Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import io
import logging
import pprint
import re

import arrow
import bson
import cachetools.func
import flask
import numpy
import pymongo
import toyplot.bitmap
import toyplot.color
import toyplot.html

import samlab.deserialize
import samlab.object

# Setup logging.
log = logging.getLogger(__name__)

# Get the web server.
from samlab.web.app import application, socketio, require_auth, require_permissions

# Get the database.
from samlab.web.app.database import database, fs


@application.route("/<allow(observations,artifacts):otype>/<oid>/content/<key>", methods=["DELETE"])
@require_auth
def delete_otype_oid_content_key(otype, oid, key):
    require_permissions(["delete"])
    oid = bson.objectid.ObjectId(oid)
    try:
        samlab.object.set_content(database, fs, otype, oid, key, value=None)
    except KeyError:
        flask.abort(404)
    return flask.jsonify()


@application.route("/<allow(observations,experiments,artifacts):otype>/attributes/keys")
@require_auth
def get_otype_attributes_keys(otype):
    require_permissions(["read"])

    keys = set()
    for obj in database[otype].find(projection={"attributes":True, "_id": False}):
        keys.update(obj["attributes"].keys())

    return flask.jsonify(keys=sorted(keys))


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/attributes/pre")
@require_auth
def get_otype_oid_attributes_pre(otype, oid):
    require_permissions(["read"])
    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if obj is None:
        flask.abort(404)

    response = flask.make_response(pprint.pformat(obj["attributes"]))
    response.headers["content-type"] = "text/plain"
    return response


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/attributes/summary")
@require_auth
def get_otype_oid_attributes_summary(otype, oid):
    require_permissions(["read"])
    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if obj is None:
        flask.abort(404)

    markup = "{" + ", ".join([key + ":&hellip;" for key in obj["attributes"]]) + "}"
    response = flask.make_response(markup)
    response.headers["content-type"] = "text/html"
    return response


@application.route("/<allow(observations,experiments,artifacts):otype>/content/keys")
@require_auth
def get_otype_content_keys(otype):
    require_permissions(["read"])

    keys = set()
    for o in database[otype].find(projection={"content": True, "_id": False}):
        keys.update(o["content"].keys())

    return flask.jsonify(keys=sorted(keys))


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/content/<key>/data")
@require_auth
def get_otype_oid_content_key_data(otype, oid, key):
    require_permissions(["read"])
    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if key not in obj["content"]:
        flask.abort(404)

    content = obj["content"][key]
    content_type = content["content-type"]
    data = fs.get(content["data"])
    headers = {
        "content-type": content_type,
    }

    begin = 0
    end = data.length
    status_code = 200

    if flask.request.headers.has_key("range"):
        status_code = 206
        headers["accept-ranges"] = "bytes"

        ranges = re.findall(r"\d+", flask.request.headers["range"])
        begin = int(ranges[0])
        if len(ranges) > 1:
            end = int(ranges[1]) + 1
        headers["content-range"] = "bytes %s-%s/%s" % (begin, end - 1, data.length)

    headers["content-length"] = str(end - begin)

    data.seek(begin)
    body = data.read(end - begin)

    response = flask.make_response((body, status_code, headers))
    response.cache_control.max_age = "300"
    response.cache_control.public = True
    return response


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/content/<key>/array/image")
@require_auth
def get_otype_oid_content_key_array_image(otype, oid, key):
    require_permissions(["read"])

    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if not key in obj["content"]:
        flask.abort(404)

    if obj["content"][key]["content-type"] != "application/x-numpy-array":
        flask.abort(400)

    data = samlab.deserialize.array(fs, obj["content"][key])

    cmap_factory, cmap_name = flask.request.args.get("colormap", "linear/Blackbody").split("/")

    if cmap_factory == "brewer":
        cmap_factory = toyplot.color.brewer
    elif cmap_factory == "linear":
        cmap_factory = toyplot.color.linear
    elif cmap_factory == "diverging":
        cmap_factory = toyplot.color.diverging
    else:
        flask.abort(400)

    try:
        colormap = cmap_factory.map(cmap_name)
    except:
        flask.abort(400)

    data = colormap.colors(data)

    stream = io.BytesIO()
    toyplot.bitmap.to_png(data, stream)

    response = flask.make_response(stream.getvalue())
    response.headers["content-type"] = "image/png"
    return response


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/content/<key>/array/metadata")
@require_auth
def get_otype_oid_content_key_array_metadata(otype, oid, key):
    require_permissions(["read"])

    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if not key in obj["content"]:
        flask.abort(404)

    if obj["content"][key]["content-type"] != "application/x-numpy-array":
        flask.abort(400)

    array = samlab.deserialize.array(fs, obj["content"][key])

    metadata = {
        "dtype": array.dtype.name,
        "ndim": array.ndim,
        "shape": array.shape,
        "size": array.size,
        "min": array.min() if array.size else None,
        "mean": array.mean() if array.size else None,
        "max": array.max() if array.size else None,
        "sum": array.sum() if array.size else None,
        }
    return flask.jsonify(metadata=metadata)


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/content/<key>/arrays/metadata")
@require_auth
def get_otype_oid_content_key_arrays_metadata(otype, oid, key):
    require_permissions(["read"])

    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if not key in obj["content"]:
        flask.abort(404)

    if obj["content"][key]["content-type"] != "application/x-numpy-arrays":
        flask.abort(400)

    with samlab.deserialize.arrays(fs, obj["content"][key]) as arrays:
        metadata = [{
            "key": key,
            "dtype": array.dtype.name,
            "shape": array.shape,
            "size": array.size,
            } for key, array in arrays.items()]
        return flask.jsonify(metadata=metadata)


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/content/<key>/arrays/<array>/data")
@require_auth
def get_otype_oid_content_key_arrays_array_data(otype, oid, key, array):
    require_permissions(["read"])

    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if not key in obj["content"]:
        flask.abort(404)

    if obj["content"][key]["content-type"] != "application/x-numpy-arrays":
        flask.abort(400)

    with samlab.deserialize.arrays(fs, obj["content"][key]) as arrays:
        if array not in arrays:
            flask.abort(404)
        return flask.jsonify(data = arrays[array].tolist())


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/content/<key>/image/metadata")
@require_auth
def get_otype_oid_content_key_image_metadata(otype, oid, key):
    require_permissions(["read"])

    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    if not key in obj["content"]:
        flask.abort(404)

    if obj["content"][key]["content-type"] not in ["image/jpeg", "image/png"]:
        flask.abort(400)

    image = samlab.deserialize.image(fs, obj["content"][key])

    return flask.jsonify(metadata={"size": image.size})


@cachetools.func.lru_cache()
def get_objects(session, otype, search):
    if search:
        return samlab.object.load(database, otype, oids=samlab.object.search(database, otype, search))

    return samlab.object.load(database, otype)


@cachetools.func.lru_cache()
def get_sorted_objects(session, otype, search, sort, direction):
    objects = get_objects(session, otype, search)
    if sort == "_id":
        objects = sorted(objects, key=lambda o: o["_id"])
    elif sort == "created":
        objects = sorted(objects, key=lambda o: o.get("created", ""))
    elif sort == "modified":
        objects = sorted(objects, key=lambda o: o.get("modified", ""))
    elif sort == "modified-by":
        objects = sorted(objects, key=lambda o: o.get("modified-by", ""))
    elif sort == "tags":
        objects = sorted(objects, key=lambda o: o.get("tags", []))
    if direction != "ascending":
        objects = objects[::-1]
    return objects


@application.route("/<allow(observations,experiments,artifacts):otype>/count")
@require_auth
def get_otype_count(otype):
    require_permissions(["read"])

    session = flask.request.args.get("session", "")
    if not session:
        flask.abort(400, "Missing session ID.")

    search = flask.request.args.get("search", "")

    objects = get_objects(session, otype, search)

    return flask.jsonify(session=session, otype=otype, search=search, count=len(objects))


@application.route("/<allow(observations,experiments,artifacts):otype>/index/<oindex>")
@require_auth
def get_otype_index_oindex(otype, oindex):
    require_permissions(["read"])

    try:
        oindex = int(oindex)
    except:
        flask.abort(400, "Index must be an integer: %s" % oindex)
    if oindex < 0:
        flask.abort(400, "Index must be a non-negative integer: %s" % oindex)

    session = flask.request.args.get("session", "")
    if not session:
        flask.abort(400, "Missing session ID.")

    search = flask.request.args.get("search", "")

    sort = flask.request.args.get("sort", "_id")
    if sort not in ["_id", "created", "modified", "modified-by", "tags"]:
        flask.abort(400, "Unknown sort type: %s" % sort)

    direction = flask.request.args.get("direction", "ascending")
    if direction not in ["ascending", "descending"]:
        flask.abort(400, "Unknown sort direction: %s" % direction)

    objects = get_sorted_objects(session, otype, search, sort, direction)
    if oindex >= len(objects):
        flask.abort(400, "Index out of range: %s" % oindex)

    oid = objects[oindex]["_id"]

    return flask.jsonify(session=session, otype=otype, search=search, sort=sort, direction=direction, oindex=oindex, oid=oid)


@application.route("/<allow(observations,experiments,artifacts):otype>/id/<oid>")
@require_auth
def get_otype_id_oid(otype, oid):
    require_permissions(["read"])

    session = flask.request.args.get("session", "")
    if not session:
        flask.abort(400, "Missing session ID.")

    search = flask.request.args.get("search", "")

    sort = flask.request.args.get("sort", "_id")
    if sort not in ["_id", "created", "modified", "modified-by", "tags"]:
        flask.abort(400, "Unknown sort type: %s" % sort)

    direction = flask.request.args.get("direction", "ascending")
    if direction not in ["ascending", "descending"]:
        flask.abort(400, "Unknown sort direction: %s" % direction)

    objects = get_sorted_objects(session, otype, search, sort, direction)
    oid = bson.objectid.ObjectId(oid)
    oindex = None
    for index, obj in enumerate(objects):
        if obj["_id"] == oid:
            oindex = index
            break

    return flask.jsonify(session=session, otype=otype, search=search, sort=sort, direction=direction, oid=oid, oindex=oindex)


@application.route("/<allow(observations,experiments,artifacts):otype>/tags")
@require_auth
def get_otype_tags(otype):
    require_permissions(["read"])

    tags = set()
    for obj in database[otype].find(projection={"tags":True, "_id": False}):
        tags.update(obj["tags"])

    return flask.jsonify(tags=sorted(tags))


def _add_modified(update):
    update["modified"] = arrow.utcnow().datetime
    if hasattr(flask.request.authorization, "username"):
        update["modified-by"] = flask.request.authorization.username
    return update


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/attributes", methods=["GET", "PUT"])
@require_auth
def get_put_otype_oid_attributes(otype, oid):
    if flask.request.method == "GET":
        require_permissions(["read"])

        oid = bson.objectid.ObjectId(oid)
        obj = database[otype].find_one({"_id": oid})

        attributes = obj["attributes"]
        return flask.jsonify(attributes=attributes)
    elif flask.request.method == "PUT":
        require_permissions(["write"])
        oid = bson.objectid.ObjectId(oid)
        obj = database[otype].find_one({"_id": oid})

        attributes = obj["attributes"]
        attributes.update(flask.request.json)

        update = {"$set": _add_modified({"attributes": attributes})}
        database[otype].update_one({"_id": oid}, update)

        socketio.emit("attribute-keys-changed", otype) # TODO: Handle this in samlab.web.app.watch_database

        return flask.jsonify()


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/tags", methods=["PUT"])
@require_auth
def put_otype_oid_tags(otype, oid):
    require_permissions(["write"])
    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    add = flask.request.json["add"]
    remove = flask.request.json["remove"]
    toggle = flask.request.json["toggle"]

    tags = set(obj["tags"])
    for tag in add:
        tags.add(tag)
    for tag in remove:
        tags.discard(tag)
    for tag in toggle:
        if tag in tags:
            tags.discard(tag)
        else:
            tags.add(tag)
    tags = list(tags)

    update = {"$set": _add_modified({"tags": tags})}
    database[otype].update_one({"_id": oid}, update)

    socketio.emit("tags-changed", otype) # TODO: Handle this in samlab.web.app.watch_database

    return flask.jsonify()


@application.route("/<allow(observations,experiments,artifacts):otype>/<oid>/plots/auto")
@require_auth
def get_otype_oid_plots_auto(otype, oid):
    require_permissions(["read"])

    width = int(flask.request.args.get("width", 500))
    height = int(flask.request.args.get("height", 500))
    yscale = flask.request.args.get("yscale", "linear")
    smoothing = float(flask.request.args.get("smoothing", "0"))

    oid = bson.objectid.ObjectId(oid)
    obj = database[otype].find_one({"_id": oid})

    colormap = toyplot.color.brewer.map("Set2")
    canvas = toyplot.Canvas(width=width, height=height)
    axes = canvas.cartesian(xlabel="Step", yscale=yscale)

    # Iterate over all content in the object.
    series_index = 0
    for name, content in obj["content"].items():
        # Only consider numpy array collections.
        if content["content-type"] != "application/x-numpy-arrays":
            continue
        arrays = samlab.deserialize.arrays(fs, content)

        # We require an array named "values" that contains a timeseries.
        if "values" not in arrays:
            continue
        values = arrays["values"]

        # Only consider 1D arrays.
        if values.ndim != 1:
            continue

        # We require an array of numbers.
        if not issubclass(values.dtype.type, numpy.number):
            continue

        # Optionally smooth the data.
        color = colormap.color(series_index)

        if smoothing:
            smoothed = []
            last = values[0]
            for value in values:
                smoothed_val = last * smoothing + (1 - smoothing) * value
                smoothed.append(smoothed_val)
                last = smoothed_val
            axes.plot(values, color=color, opacity=0.3, style={"stroke-width":1}, title=name)
            axes.plot(smoothed, color=color, opacity=1, style={"stroke-width":2}, title="{} (smoothed)".format(name))
        else:
            axes.plot(values, color=color, opacity=1, style={"stroke-width":2}, title=name)

        series_index += 1

    result = {}
    result["plot"] = toyplot.html.tostring(canvas)

    return flask.jsonify(result)


