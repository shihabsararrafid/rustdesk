import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class EmployeeManagementModel extends ChangeNotifier {
  final http.Client client;
  final Future<String> Function() token;
  final String origin;
  bool loading = false;
  bool signedIn = false;
  String error = '';
  String username = '';
  Map<String, dynamic> policy = {};
  List<Map<String, dynamic>> peers = [];
  int offset = 0;
  int total = 0;
  String search = '';
  int _generation = 0;
  bool _disposed = false;

  EmployeeManagementModel({required this.client, required this.token, required this.origin});

  Future<Map<String, dynamic>> _get(String path, String bearer) async {
    final response = await client.get(Uri.parse('$origin$path'), headers: {
      'Authorization': 'Bearer $bearer',
    }).timeout(const Duration(seconds: 12));
    if (response.statusCode == 401) {
      signedIn = false;
      throw StateError('Sign in to your employee account');
    }
    if (response.statusCode != 200) throw StateError('Management service unavailable (${response.statusCode})');
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<void> refresh() async {
    final generation = ++_generation;
    loading = true; error = ''; notifyListeners();
    try {
      final bearer = await token();
      if (bearer.isEmpty) { signedIn = false; peers = []; return; }
      final me = await _get('/api/management/me', bearer);
      final query = Uri(queryParameters: {'limit': '25', 'offset': '$offset', 'q': search}).query;
      final data = await _get('/api/management/clients?$query', bearer);
      if (_disposed || generation != _generation) return;
      signedIn = true;
      username = (me['user'] as Map)['name'] as String;
      policy = Map<String, dynamic>.from(me['policy'] as Map);
      peers = (data['items'] as List).map((p) => Map<String, dynamic>.from(p as Map)).toList();
      total = data['total'] as int;
    } catch (e) {
      if (!_disposed && generation == _generation) { error = e.toString(); peers = []; }
    } finally {
      if (!_disposed && generation == _generation) { loading = false; notifyListeners(); }
    }
  }

  bool permits(String key) => signedIn && policy[key] == true;

  @override
  void dispose() { _disposed = true; _generation++; client.close(); super.dispose(); }
}
