import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import '../../common.dart';
import '../../common/widgets/login.dart';
import '../../models/employee_management_model.dart';

class EmployeeDirectoryGate extends StatefulWidget {
  final Widget child;
  const EmployeeDirectoryGate({Key? key, required this.child}) : super(key: key);
  @override
  State<EmployeeDirectoryGate> createState() => _EmployeeDirectoryGateState();
}

class _EmployeeDirectoryGateState extends State<EmployeeDirectoryGate> {
  EmployeeManagementModel? model;
  final search = TextEditingController();
  final directId = TextEditingController();

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  Future<void> _initialize() async {
    final url = await bind.mainGetOption(key: 'employee-management-url');
    if (!mounted || url.isEmpty) return;
    final next = EmployeeManagementModel(client: http.Client(), origin: url.replaceAll(RegExp(r'/$'), ''),
      token: () async => bind.mainGetLocalOption(key: 'access_token'));
    next.addListener(_changed);
    setState(() => model = next);
    await next.refresh();
  }

  void _changed() { if (mounted) setState(() {}); }

  @override
  void dispose() {
    model?.removeListener(_changed); model?.dispose(); search.dispose(); directId.dispose(); super.dispose();
  }

  Future<void> _login() async { await loginDialog(); await model?.refresh(); }

  @override
  Widget build(BuildContext context) {
    final m = model;
    if (m == null) return widget.child;
    final directory = Padding(padding: const EdgeInsets.all(20), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        const Expanded(child: Text('Clients', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600))),
        IconButton(tooltip: 'Refresh', onPressed: m.loading ? null : m.refresh, icon: const Icon(Icons.refresh)),
        IconButton(tooltip: 'Management console', icon: const Icon(Icons.admin_panel_settings_outlined),
          onPressed: () => launchUrl(Uri.parse('${m.origin}/console'), mode: LaunchMode.externalApplication)),
        TextButton(onPressed: _login, child: Text(m.signedIn ? m.username : 'Sign in')),
      ]),
      if (m.loading) const LinearProgressIndicator(),
      if (m.error.isNotEmpty) Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Text(m.error, style: TextStyle(color: Theme.of(context).colorScheme.error))),
      if (!m.signedIn && !m.loading) Expanded(child: Center(child: ElevatedButton(onPressed: _login, child: const Text('Sign in'))))
      else ...[
        const SizedBox(height: 16),
        Row(children: [Expanded(child: TextField(controller: search, decoration: const InputDecoration(labelText: 'Search clients', prefixIcon: Icon(Icons.search)),
          onSubmitted: (value) { m.search = value; m.offset = 0; m.refresh(); })),
          IconButton(tooltip: 'Search', onPressed: () { m.search = search.text; m.offset = 0; m.refresh(); }, icon: const Icon(Icons.search))]),
        const SizedBox(height: 12),
        Row(children: [Expanded(child: TextField(controller: directId, decoration: const InputDecoration(labelText: 'RustDesk ID'),
          onSubmitted: (value) { if (m.permits('allow_remote_control')) connect(context, value); })),
          IconButton(tooltip: 'Connect', onPressed: !m.permits('allow_remote_control') ? null : () => connect(context, directId.text), icon: const Icon(Icons.arrow_forward))]),
        const SizedBox(height: 12),
        Expanded(child: m.peers.isEmpty ? const Center(child: Text('No clients found')) : ListView.separated(
          itemCount: m.peers.length, separatorBuilder: (_, __) => const Divider(height: 1), itemBuilder: (context, index) {
            final peer = m.peers[index]; final id = peer['rustdesk_id'] as String;
            return ListTile(contentPadding: EdgeInsets.zero, title: Text(peer['customer_name'] as String),
              subtitle: Text('${peer['device_label']} · $id · Presence unknown'),
              trailing: SizedBox(width: 96, child: Row(children: [
                IconButton(tooltip: 'File transfer', onPressed: !m.permits('allow_file_transfer') ? null : () => connect(context, id, isFileTransfer: true), icon: const Icon(Icons.folder_outlined)),
                IconButton(tooltip: 'Connect', onPressed: !m.permits('allow_remote_control') ? null : () => connect(context, id), icon: const Icon(Icons.arrow_forward)),
              ])));
          })),
        Row(mainAxisAlignment: MainAxisAlignment.end, children: [Text('${m.total} clients'),
          IconButton(tooltip: 'Previous page', onPressed: m.loading || m.offset == 0 ? null : () { m.offset = (m.offset - 25).clamp(0, m.total).toInt(); m.refresh(); }, icon: const Icon(Icons.chevron_left)),
          IconButton(tooltip: 'Next page', onPressed: m.loading || m.offset + 25 >= m.total ? null : () { m.offset += 25; m.refresh(); }, icon: const Icon(Icons.chevron_right))]),
      ],
    ]));
    return DefaultTabController(length: 2, child: Column(children: [
      const TabBar(tabs: [Tab(text: 'Company clients'), Tab(text: 'Connections')]),
      Expanded(child: TabBarView(children: [directory, widget.child])),
    ]));
  }
}
