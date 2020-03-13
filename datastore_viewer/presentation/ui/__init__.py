import json
import base64
import datetime
import os

import flask.views
import urllib.parse

from logging import getLogger
from collections import defaultdict
from google.cloud import datastore

from datastore_viewer.infrastructure import DatastoreViewerRepository

logger = getLogger(__name__)


class DashboardView(flask.views.MethodView):
    def get(self):
        project_name = flask.request.args.get('project_name')
        if project_name is not None and len(project_name) > 0:
            return flask.redirect(f'/datastore_viewer/projects/{project_name}')

        return flask.render_template(
            'dashboard.html',
            project_name=os.environ.get('GOOGLE_CLOUD_PROJECT', '')
        )


class ProjectView(flask.views.MethodView):
    def _build_redirect_path(self, **kwargs):
        doc = {}
        for k, v in flask.request.args.items():
            doc[k] = v
        doc.update(kwargs)

        return f'{flask.request.path}?{urllib.parse.urlencode(doc)}'

    def get(self, project_name: str):
        namespace = flask.request.args.get('namespace')
        cursor = base64.b64decode(flask.request.args.get('cursor', '')).decode('utf-8')
        repository = DatastoreViewerRepository(
            project_name=project_name,
            namespace=namespace,
        )

        current_namespace = repository.current_namespace()
        namespaces = repository.fetch_namespaces()
        kinds = repository.fetch_kinds()
        properties_by_kind = repository.fetch_parent_properties()

        current_kind = flask.request.args.get('kind')
        if current_kind is None and len(kinds) > 0:
            return flask.redirect(self._build_redirect_path(
                kind=kinds[0],
            ))

        current_kind_properties = properties_by_kind.get(current_kind, [])

        entities, next_cursor = repository.fetch_entities(
            kind=current_kind,
            limit=20,
            cursor=cursor,
        )

        return flask.render_template(
            'project_dashboard.html',
            project_name=project_name,
            namespaces=namespaces,
            current_namespace=current_namespace,
            kinds=kinds,
            current_kind=current_kind,
            current_kind_properties=current_kind_properties,
            entities=entities,
            has_entities=len(entities) > 0,
            next_cursor=base64.b64encode(next_cursor).decode('ascii'),
        )

    def post(self, project_name: str):
        namespace = flask.request.args.get('namespace')
        current_kind = flask.request.args.get('kind')
        repository = DatastoreViewerRepository(
            project_name=project_name,
            namespace=namespace,
        )

        action = flask.request.form.get('action')
        serialized_key = flask.request.form.get('key')
        logger.info(f'action = {action}, key = {serialized_key}')
        if action == 'delete' and serialized_key is not None:
            self._delete_entity(
                repository=repository,
                serialized_key=serialized_key
            )
        elif action == 'delete_all':
            repository.delete_all(kind=current_kind)

        return flask.redirect(self._build_redirect_path(t=datetime.datetime.utcnow().timestamp()))

    def _delete_entity(self, repository, serialized_key: str):
        key_path = json.loads(base64.b64decode(serialized_key))
        key = repository.build_key_by_flat_path(key_path=key_path)
        repository.delete(key)


class EntityView(flask.views.MethodView):
    def get(self, project_name: str):
        namespace = flask.request.args.get('namespace')
        repository = DatastoreViewerRepository(
            project_name=project_name,
            namespace=namespace,
        )

        serialized_key = flask.request.args.get('key')
        key_path = json.loads(base64.b64decode(serialized_key))
        key = repository.build_key_by_flat_path(key_path=key_path)
        entity = repository.fetch_entity(key=key)

        return flask.jsonify({
            'project_name': project_name,
            'key':str(key),
            'entity': str(entity)
        })


class ProjectAPIView(flask.views.MethodView):
    def _property_type_checker(self, prop):
        if isinstance(prop, str):
            return "string"
        elif isinstance(prop, int):
            return "integer"
        elif isinstance(prop, float):
            return "float"
        elif isinstance(prop, bool):
            return "boolean"
        elif isinstance(prop, datetime.datetime):
            return "timestamp"
        elif isinstance(prop, datastore.Key):
            return "key"
        else:
            return "null"

    def _build_entity_json(self, entity, properties):
        entity_dict = {
            "entity": {
                "key": {
                    "partitionId": {
                        "projectId": entity.key.project
                    },
                    "path": entity.key.path
                },
                "properties": [],
            },
            "URLSafeKey": entity._serialized_key
        }

        for property in properties:
            if self._property_type_checker(entity[property]) == "key":
                value = entity[property].path
            else:
                value = entity[property]

            entity_dict['entity']['properties'].append(
                {
                    "property_name": property,
                    "value_type": self._property_type_checker(entity[property]),
                    "value": value,
                    "index": True,
                },
            )

        return entity_dict

    def get(self, project_name: str, kind: str):
        cursor = base64.b64decode(flask.request.args.get('cursor', '')).decode('utf-8')
        repository = DatastoreViewerRepository(project_name=project_name)

        properties_by_kind = repository.fetch_parent_properties()
        current_kind = kind
        current_kind_properties = properties_by_kind.get(current_kind, [])

        entities, next_cursor = repository.fetch_entities(
            kind=current_kind,
            limit=20,
            cursor=cursor,
        )

        entities_array = []
        for entity in entities:
            entities_array.append(self._build_entity_json(entity, current_kind_properties))

        entities_json = defaultdict(list)
        entities_json['entityResults'] = entities_array

        return flask.jsonify(entities_json)


class EntityAPIView(flask.views.MethodView):
    def _property_type_checker(self, prop):
        if isinstance(prop, str):
            return "string"
        elif isinstance(prop, int):
            return "integer"
        elif isinstance(prop, float):
            return "float"
        elif isinstance(prop, bool):
            return "boolean"
        elif isinstance(prop, datetime.datetime):
            return "timestamp"
        elif isinstance(prop, datastore.Key):
            return "key"
        else:
            return "null"

    def _build_entity_json(self, entity, properties):
        entity_dict = {
            "entity": {
                "key": {
                    "partitionId": {
                        "projectId": entity.key.project
                    },
                    "path": entity.key.path
                },
                "properties": [],
            },
            "URLSafeKey": entity._serialized_key
        }

        for property in properties:
            if self._property_type_checker(entity[property]) == "key":
                value = entity[property].path
            else:
                value = entity[property]

            entity_dict['entity']['properties'].append(
                {
                    "property_name": property,
                    "value_type": self._property_type_checker(entity[property]),
                    "value": value,
                    "index": True,
                },
            )

        return entity_dict

    def get(self, project_name: str, kind: str, url_safe_key: str):
        repository = DatastoreViewerRepository(project_name=project_name)
        key_path = json.loads(base64.b64decode(url_safe_key))
        key = repository.build_key_by_flat_path(key_path=key_path)
        entity = repository.fetch_entity(key=key)

        properties_by_kind = repository.fetch_parent_properties()
        current_kind = kind
        current_kind_properties = properties_by_kind.get(current_kind, [])

        return flask.jsonify({
            "entityResult": self._build_entity_json(entity, current_kind_properties)
        })


class KindAPIView(flask.views.MethodView):
    def get(self, project_name: str):
        repository = DatastoreViewerRepository(project_name=project_name)
        properties_by_kind = repository.fetch_parent_properties()

        kinds_json = defaultdict(list)
        kinds_json['kindResults'] = []

        for kind in properties_by_kind:
            kind_properties = properties_by_kind.get(kind, [])
            kind_dict = {
                "kind": kind,
                "indexed_properties": list(map(lambda x: {"property_name": x}, kind_properties))}
            kinds_json['kindResults'].append(kind_dict)

        return flask.jsonify(kinds_json)


class ProjectListAPIView(flask.views.MethodView):
    def get(self):
        if os.environ['GOOGLE_CLOUD_PROJECT']:
            project_name = os.environ['GOOGLE_CLOUD_PROJECT']
        else:
            project_name = ''

        return flask.jsonify({
            "projectResult": {
                "project_name": project_name
            }
        })


def register_views(blueprint):
    blueprint.add_url_rule(
        '/datastore_viewer',
        view_func=DashboardView.as_view(name='dashboard'),
        methods=['GET']
    )

    blueprint.add_url_rule(
        '/datastore_viewer/projects/<string:project_name>',
        view_func=ProjectView.as_view(name='project_view'),
        methods=['GET', 'POST']
    )

    blueprint.add_url_rule(
        '/datastore_viewer/projects/<string:project_name>/view_entity',
        view_func=EntityView.as_view(name='entity_view'),
        methods=['GET']
    )

    blueprint.add_url_rule(
        '/datastore_viewer/api/projects/<string:project_name>/kinds/<string:kind>/entities',
        view_func=ProjectAPIView.as_view(name='project_api_view'),
        methods=['GET']
    )

    blueprint.add_url_rule(
        '/datastore_viewer/api/projects/<string:project_name>/kinds/<string:kind>/entities/<string:url_safe_key>',
        view_func=EntityAPIView.as_view(name='entity_api_view'),
        methods=['GET']
    )

    blueprint.add_url_rule(
        '/datastore_viewer/api/projects/<string:project_name>/kinds',
        view_func=KindAPIView.as_view(name='kind_api_view'),
        methods=['GET']
    )

    blueprint.add_url_rule(
        '/datastore_viewer/api/projects',
        view_func=ProjectListAPIView.as_view(name='project_list_api_view'),
        methods=['GET']
    )
