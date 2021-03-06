#!flask/bin/python
from operator import itemgetter

import itertools

from flask import Flask, jsonify
from flask import json
from flask import request
from flask_graphql import GraphQLView
from flask_restful import Resource, Api, reqparse
from json import loads, dumps
import inflection
import xmltodict
from dateutil.parser import parse

from flask_cors import CORS

import uuid

from core.schema import schema
from core.database import Database
from core.sql_queries import *
from resources.mapping import mappings

app = Flask(__name__)
api = Api(app)

db = Database()

CORS(app)

parser = reqparse.RequestParser()


def convert_datetime_columns(data, columns):
    selected_element = data[0]
    keys = list(selected_element.keys())

    intersection = set(keys).intersection(columns)

    for d in data:
        d.update((k, parse(v).date().strftime('%Y-%m-%d %H:%M:%S')) for k, v in d.iteritems() if
                 k in intersection and v is not None)
    return data


def convert_boolean_columns(data, columns):
    selected_element = data[0]
    keys = list(selected_element.keys())

    intersection = set(keys).intersection(columns)

    for d in data:
        d.update((k, True if v == 'true' else False) for k, v in d.iteritems() if
                 k in intersection and v is not None)
    return data


def to_dict(input_ordered_dict):
    return loads(dumps(input_ordered_dict))


def check_registered_facility(facility_uuid):
    facility = db.query_one("select * from facility where uuid = '" + facility_uuid + "'")
    if facility:
        return True
    return False


def get_sync_item(sync_item, sync_item_type, facility):
    if isinstance(sync_item, dict) and sync_item:
        print sync_item['@containedType']
        obj = {}
        if sync_item['@containedType'] == sync_item_type:
            data_dict = xmltodict.parse(sync_item['content'])
            data_imported = to_dict(data_dict)

            data = data_imported[sync_item_type]
            row = {}
            for k, v in data.items():
                row[inflection.underscore(k)] = v['#text']
            obj['facility'] = facility
            obj['state'] = sync_item['@state']
            obj['data'] = row
            return obj


def get_sync_items(sync_items, sync_item_types, facility):
    items = []

    if isinstance(sync_items, dict):
        for sync_item_type, table_name in sync_item_types.items():
            item = get_sync_item(sync_items, sync_item_type, facility)
            if item is not None:
                item['table'] = table_name
                item['data']['facility'] = item['facility']
                item['data']['state'] = item['state']
                items.append(item)
    elif isinstance(sync_items, list):
        for sync_item_type, table_name in sync_item_types.items():
            for sync_item in sync_items:
                item = get_sync_item(sync_item, sync_item_type, facility)
                if item is not None:
                    item['table'] = table_name
                    item['data']['facility'] = item['facility']
                    item['data']['state'] = item['state']
                    items.append(item)

    sorted_items = sorted(items, key=itemgetter('table'))

    for key, value in itertools.groupby(sorted_items, key=itemgetter('table')):
        data_to_be_inserted = [v['data'] for v in list(value)]
        if key == 'obs':
            obs_template = {
                'person': None, 'concept': None, 'encounter': None, 'order': None, 'obs_datetime': None,
                'location': None, 'obs_group': None, 'accession_number': None, 'value_group': None,
                'value_boolean': None, 'value_coded': None, 'value_coded_name': None, 'value_drug': None,
                'value_datetime': None, 'value_numeric': None, 'value_modifier': None, 'value_text': None,
                'value_complex': None, 'comments': None, 'creator': None, 'date_created': None, 'voided': None,
                'voided_by': None, 'date_voided': None, 'void_reason': None, 'uuid': None, 'facility': None,
                'state': None, 'previous_version': None
            }
            final_data = [dict(obs_template, **x) for x in data_to_be_inserted]
            final_data = convert_datetime_columns(final_data,
                                                  ['date_created', 'value_datetime', 'obs_datetime', 'date_voided'])
            final_data = convert_boolean_columns(final_data, ['voided'])

            db.insert_bulk(add_obs, final_data)
        elif key == 'encounter':
            encounter_template = {
                'encounter_type': None, 'patient': None, 'location': None, 'form': None, 'encounter_datetime': None,
                'creator': None, 'date_created': None, 'voided': None, 'voided_by': None, 'date_voided': None,
                'void_reason': None, 'changed_by': None, 'date_changed': None, 'visit': None, 'uuid': None,
                'facility': None, 'state': None
            }

            final_data = [dict(encounter_template, **x) for x in data_to_be_inserted]
            final_data = convert_datetime_columns(final_data,
                                                  ['encounter_datetime', 'date_changed', 'date_voided', 'date_created'])
            final_data = convert_boolean_columns(final_data, ['voided'])
            db.insert_bulk(add_encounter, final_data)

        elif key == 'encounter_provider':
            encounter_provider_template = {
                'encounter': None, 'provider': None, 'encounter_role': None, 'creator': None, 'date_created': None,
                'uuid': None
            }
            final_data = [dict(encounter_provider_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_encounter_provider, final_data)

        elif key == 'person':
            person_template = {
                'gender': None, 'birthdate': None, 'birthdate_estimated': None, 'dead': None, 'death_date': None,
                'cause_of_death': None, 'creator': None, 'date_created': None, 'changed_by': None, 'date_changed': None,
                'voided': None, 'voided_by': None, 'date_voided': None, 'void_reason': None, 'uuid': None,
                'facility': None, 'state': None, 'deathdate_estimated': None, 'birthtime': None
            }
            final_data = [dict(person_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_person, final_data)
        elif key == 'patient':
            patient_template = {
                'patient': None, 'creator': None, 'date_created': None, 'changed_by': None, 'date_changed': None,
                'voided': None, 'voided_by': None, 'date_voided': None, 'void_reason': None, 'allergy_status': None,
                'facility': None, 'state': None
            }
            final_data = [dict(patient_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_patient, final_data)
        elif key == 'person_name':
            person_name_template = {
                'preferred': None, 'person': None, 'prefix': None, 'given_name': None, 'middle_name': None,
                'family_name_prefix': None, 'family_name': None, 'family_name2': None, 'family_name_suffix': None,
                'degree': None, 'creator': None, 'date_created': None, 'voided': None, 'voided_by': None,
                'date_voided': None, 'void_reason': None, 'changed_by': None, 'date_changed': None, 'uuid': None,
                'facility': None, 'state': None
            }
            final_data = [dict(person_name_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_person_name, final_data)
        elif key == 'person_attribute':
            person_attribute_template = {
                'person': None, 'value': None, 'person_attribute_type': None, 'creator': None, 'date_created': None,
                'changed_by': None, 'date_changed': None, 'voided': None, 'voided_by': None, 'date_voided': None,
                'void_reason': None, 'uuid': None, 'facility': None, 'state': None
            }
            final_data = [dict(person_attribute_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_person_attribute, final_data)
        elif key == 'patient_identifier':
            patient_identifier_template = {
                'patient': None, 'identifier': None, 'identifier_type': None, 'preferred': None, 'location': None,
                'creator': None, 'date_created': None, 'date_changed': None, 'changed_by': None, 'voided': None,
                'voided_by': None, 'date_voided': None, 'void_reason': None, 'uuid': None, 'facility': None,
                'state': None
            }
            final_data = [dict(patient_identifier_template, **x) for x in data_to_be_inserted]
            final_data = convert_datetime_columns(final_data,
                                                  ['date_created'])
            final_data = convert_boolean_columns(final_data, ['voided', 'preferred'])
            db.insert_bulk(add_patient_identifier, final_data)
        elif key == 'visit':
            visit_template = {
                'patient': None, 'visit_type': None, 'date_started': None, 'date_stopped': None,
                'indication_concept': None, 'location': None, 'creator': None, 'date_created': None, 'changed_by': None,
                'date_changed': None, 'voided': None, 'voided_by': None, 'date_voided': None, 'void_reason': None,
                'uuid': None, 'facility': None, 'state': None
            }
            final_data = [dict(visit_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_visit, final_data)
        elif key == 'person_address':
            person_address_template = {
                'person': None, 'preferred': None, 'address1': None, 'address2': None, 'city_village': None,
                'state_province': None, 'postal_code': None, 'country': None, 'latitude': None, 'longitude': None,
                'start_date': None, 'end_date': None, 'creator': None, 'date_created': None, 'voided': None,
                'voided_by': None, 'date_voided': None, 'void_reason': None, 'county_district': None, 'address3': None,
                'address4': None, 'address5': None, 'address6': None, 'date_changed': None, 'changed_by': None,
                'uuid': None, 'facility': None, 'state': None
            }
            final_data = [dict(person_address_template, **x) for x in data_to_be_inserted]
            db.insert_bulk(add_person_address, final_data)


def process_many_sync_rows(rows, sync_item_types, facility):
    for row in rows:
        dic = xmltodict.parse(row['payload'])
        sync_items = to_dict(dic)['items']['SyncItem']
        get_sync_items(sync_items, sync_item_types, facility)


def process_many_sync_row(data, sync_item_types, facility):
    dic = xmltodict.parse(data)
    sync_items = to_dict(dic)['items']['SyncItem']

    get_sync_items(sync_items, sync_item_types, facility)


@app.route('/api', methods=['POST'])
def post_data():
    if request.headers['Content-Type'] == 'text/plain':
        return "Text Message: " + request.data

    elif request.headers['Content-Type'] == 'application/json':
        return "JSON Message: " + json.dumps(request.json)

    elif request.headers['Content-Type'] == 'application/octet-stream':
        f = open('./binary', 'wb')
        f.write(request.data)
        f.close()
        return "Binary message written!"
    elif request.headers['Content-Type'] == 'text/xml' or request.headers['Content-Type'] == 'application/xml':
        facility_id = request.headers['Ugandaemr-Sync-Facility-Id']
        facility_exists = check_registered_facility(facility_id)
        if facility_exists:
            process_many_sync_row(request.data, mappings, facility_id)
            return jsonify({"response": "Successful", 'inserted': 6})
        else:
            return jsonify({
                "response": "Unsuccessful",
                'message': 'Your facility is not registered please send a request to register'
            })
    else:
        return "415 Unsupported Media Type ;)"


@app.route('/api/facility', methods=['POST'])
def get_facility():
    if request.headers['Content-Type'] == 'application/json':
        data = request.json
        facility_name = data['name']
        facility_id = str(uuid.uuid4())
        if facility_name:
            db.insert(add_facility, {'name': facility_name, 'uuid': facility_id})
            return jsonify({
                "response": "Successful",
                'uuid': facility_id
            })
        else:
            return jsonify({
                "response": "Unsuccessful",
                'message': 'You have not supplied the facility name'
            })
    else:
        return "415 Unsupported Media Type ;)"


app.add_url_rule('/api/query', view_func=GraphQLView.as_view('graphql', schema=schema, graphiql=True))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
