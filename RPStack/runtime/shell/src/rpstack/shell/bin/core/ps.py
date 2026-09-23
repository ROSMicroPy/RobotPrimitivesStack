from rpstack.shell.support import require_node, json

def run(context, arguments):
    node = require_node(context)
    print("ID\tSTATE\t\tKIND\t\tNAME")
    for item in node.tasks.snapshot():
        print("{}\t{}\t{}\t{}".format(item['id'], item['state'], item['kind'], item['name']))
