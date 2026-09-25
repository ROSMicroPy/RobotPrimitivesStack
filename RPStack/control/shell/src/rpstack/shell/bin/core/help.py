# Print available commands grouped into core, optional, and external installations.
def run(context, arguments):
    groups = context.commands.groups()
    for group in ('core', 'optional', 'external'):
        names = sorted(groups.get(group, []))
        if names:
            print(group + ': ' + ' '.join(names))
