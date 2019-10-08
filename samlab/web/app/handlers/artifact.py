# Copyright 2018, National Technology & Engineering Solutions of Sandia, LLC
# (NTESS).  Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
# Government retains certain rights in this software.

import logging
import pprint

import arrow
import bson
import flask
import toyplot.color
import toyplot.html

import samlab.deserialize
import samlab.web.app.handlers.common

# Setup logging.
log = logging.getLogger(__name__)

# Get the web server.
from samlab.web.app import application, socketio, require_auth, require_permissions

# Get the database.
from samlab.web.app.database import database, fs


@application.route("/artifacts/<exclude(count,tags):oid>", methods=["GET", "DELETE"])
@require_auth
def get_delete_artifacts_artifact(oid):
    oid = bson.objectid.ObjectId(oid)

    if flask.request.method == "GET":
        return samlab.web.app.handlers.common.get_otype_oid("artifacts", oid)

    elif flask.request.method == "DELETE":
        require_permissions(["delete"])
        samlab.artifact.delete(database, fs, oid)
        return flask.jsonify()


@application.route("/artifacts/<artifact>/plots/training-loss")
@require_auth
def get_artifacts_artifact_plots_training_loss(artifact):
    require_permissions(["read"])

    width = int(flask.request.args.get("width", 500))
    height = int(flask.request.args.get("height", 500))
    scale = flask.request.args.get("scale", "linear")
    training = True if flask.request.args.get("training", "true") == "true" else False
    validation = True if flask.request.args.get("validation", "true") == "true" else False
    test = True if flask.request.args.get("test", "true") == "true" else False

    artifact = bson.objectid.ObjectId(artifact)
    artifact = database.artifacts.find_one({"_id": artifact})

    result = {
        "minimum_training_loss": None,
        "minimum_validation_loss": None,
        "minimum_test_loss": None,
        }

    palette = toyplot.color.Palette()
    canvas = toyplot.Canvas(width=width, height=height)

    axes = canvas.cartesian(xlabel="Training Epoch", ylabel="Loss", yscale=scale)
    labels = []
    if training and "training-losses" in artifact["content"]:
        training_losses = samlab.deserialize.array(fs, artifact["content"]["training-losses"])
        if training_losses.size:
            mark = axes.plot(training_losses, color=palette[0])
            labels.append(mark.markers[0] + " training")
            result["minimum_training_loss"] = training_losses.min()

    if validation and "validation-losses" in artifact["content"]:
        validation_losses = samlab.deserialize.array(fs, artifact["content"]["validation-losses"])
        if validation_losses.size:
            mark = axes.plot(validation_losses, color=palette[1])
            labels.append(mark.markers[0] + " validation")
            result["minimum_validation_loss"] = validation_losses.min()

    if test and "test-losses" in artifact["content"]:
        test_losses = samlab.deserialize.array(fs, artifact["content"]["test-losses"])
        if test_losses.size:
            mark = axes.plot(test_losses, color=palette[2])
            labels.append(mark.markers[0] + " test")
            result["minimum_test_loss"] = test_losses.min()

    axes.label.text = " ".join(labels)

    result["plot"] = toyplot.html.tostring(canvas)

    return flask.jsonify(result)


@application.route("/artifacts/<artifact>/plots/training-accuracy")
@require_auth
def get_artifacts_artifact_plots_training_accuracy(artifact, width=500, height=500):
    require_permissions(["read"])
    artifact = bson.objectid.ObjectId(artifact)
    artifact = database.artifacts.find_one({"_id": artifact})

    result = {}

    palette = toyplot.color.Palette()
    canvas = toyplot.Canvas(width=width, height=height)

    axes = canvas.cartesian(xlabel="Training Epoch", ylabel="Accuracy")
    labels = []
    if "training-accuracies" in artifact["content"]:
        training_accuracies = samlab.deserialize.array(fs, artifact["content"]["training-accuracies"])
        mark = axes.plot(training_accuracies, color=palette[0])
        labels.append(mark.markers[0] + " training")
        result["maximum_training_accuracy"] = training_accuracies.max()
    else:
        result["maximum_training_accuracy"] = None

    if "validation-accuracies" in artifact["content"]:
        validation_accuracies = samlab.deserialize.array(fs, artifact["content"]["validation-accuracies"])
        mark = axes.plot(validation_accuracies, color=palette[1])
        labels.append(mark.markers[0] + " validation")
        result["maximum_validation_accuracy"] = validation_accuracies.max()
    else:
        result["maximum_validation_accuracy"] = None

    if "test-accuracies" in artifact["content"]:
        test_accuracies = samlab.deserialize.array(fs, artifact["content"]["test-accuracies"])
        mark = axes.plot(test_accuracies, color=palette[2])
        labels.append(mark.markers[0] + " test")
        result["maximum_test_accuracy"] = test_accuracies.max()
    else:
        result["maximum_test_accuracy"] = None

    axes.label.text = " ".join(labels)

    result["plot"] = toyplot.html.tostring(canvas)

    return flask.jsonify(result)
