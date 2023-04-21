with open('/tmp/test1', 'w') as t1f:
    t1f.write("test\n" * 1024 * 1024 * 200)

with open('/tmp/test1', 'r') as t1f:
    for f in iter(lambda: t1f.read(1024 * 1024 * 50), ''):
        pass
