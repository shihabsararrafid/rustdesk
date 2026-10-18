import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_hbb/models/employee_management_model.dart';

void main() {
  test('signed out does not request directory', () async {
    final model = EmployeeManagementModel(origin: 'https://example.com', token: () async => '',
      client: MockClient((_) async => throw StateError('Unexpected HTTP')));
    await model.refresh();
    expect(model.signedIn, false); expect(model.peers, isEmpty); model.dispose();
  });
  test('all clients and unknown presence are retained', () async {
    final model = EmployeeManagementModel(origin: 'https://example.com', token: () async => 'token',
      client: MockClient((request) async => http.Response(jsonEncode(request.url.path.endsWith('/me')
        ? {'user': {'name': 'employee'}, 'policy': {'allow_remote_control': true}}
        : {'items': [{'rustdesk_id': '123', 'presence': 'unknown'}], 'total': 1}), 200)));
    await model.refresh();
    expect(model.signedIn, true); expect(model.permits('allow_remote_control'), true);
    expect(model.permits('allow_file_transfer'), false); expect(model.peers.single['presence'], 'unknown'); model.dispose();
  });
  test('revoked login and service failure are explicit', () async {
    final model = EmployeeManagementModel(origin: 'https://example.com', token: () async => 'revoked',
      client: MockClient((_) async => http.Response('{}', 401)));
    await model.refresh(); expect(model.signedIn, false); expect(model.error, isNotEmpty); model.dispose();
  });
}
