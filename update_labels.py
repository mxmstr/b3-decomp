import re

def parse_gdl(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    graph = {}
    nodes = re.findall(r'node: { title: "([^"]+)" label: "([^"]+)"', content)
    edges = re.findall(r'edge: { sourcename: "([^"]+)" targetname: "([^"]+)"', content)

    for title, label in nodes:
        graph[title] = {'label': label, 'children': [], 'parents': []}

    for source, target in edges:
        if source in graph and target in graph:
            graph[source]['children'].append(target)
            graph[target]['parents'].append(source)

    return graph

def find_node_by_label(graph, label):
    for title, node in graph.items():
        if node['label'] == label:
            return title
    return None

def compare_nodes(demo_node, retail_node):
    # Allow for some flexibility in matching
    children_diff = abs(len(demo_node['children']) - len(retail_node['children']))
    parents_diff = abs(len(demo_node['parents']) - len(retail_node['parents']))

    # print(f"Comparing nodes: demo children: {len(demo_node['children'])}, retail children: {len(retail_node['children'])}")
    # print(f"Comparing nodes: demo parents: {len(demo_node['parents'])}, retail parents: {len(retail_node['parents'])}")

    return children_diff <= 2 and parents_diff <= 2

def match_graphs(demo_graph, retail_graph, start_label):
    demo_entry = find_node_by_label(demo_graph, start_label)
    retail_entry = find_node_by_label(retail_graph, start_label)

    if not demo_entry or not retail_entry:
        print(f"Starting node with label '{start_label}' not found in one of the graphs.")
        return {}

    mapping = {}
    queue = [(demo_entry, retail_entry)]
    visited = set()

    while queue:
        demo_title, retail_title = queue.pop(0)

        if (demo_title, retail_title) in visited:
            continue
        visited.add((demo_title, retail_title))

        demo_node = demo_graph[demo_title]
        retail_node = retail_graph[retail_title]

        if compare_nodes(demo_node, retail_node):
            mapping[retail_title] = demo_title

            # Add children to the queue for further matching
            for demo_child in demo_node['children']:
                for retail_child in retail_node['children']:
                    if (demo_child, retail_child) not in visited:
                        queue.append((demo_child, retail_child))
    return mapping

def update_labels(retail_content, mapping, demo_graph, retail_graph):
    updated_content = retail_content
    for retail_title, demo_title in mapping.items():
        demo_label = demo_graph[demo_title]['label']
        retail_label_old = retail_graph[retail_title]['label']

        old_node_str = f'node: {{ title: "{retail_title}" label: "{retail_label_old}"'
        new_node_str = f'node: {{ title: "{retail_title}" label: "{demo_label}"'

        updated_content = updated_content.replace(old_node_str, new_node_str)

    return updated_content


if __name__ == '__main__':
    demo_graph = parse_gdl('graph_b3_demo.gdl')
    retail_graph = parse_gdl('graph_b3_retail.gdl')

    mapping = match_graphs(demo_graph, retail_graph, 'CB3Game::Construct')
    print("Found {} matches.".format(len(mapping)))

    with open('graph_b3_retail.gdl', 'r') as f:
        retail_content = f.read()

    updated_content = update_labels(retail_content, mapping, demo_graph, retail_graph)

    with open('graph_b3_retail.gdl', 'w') as f:
        f.write(updated_content)

    print("Updated labels written to graph_b3_retail.gdl")
