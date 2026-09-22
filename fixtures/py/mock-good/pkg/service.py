def notify(client, user_id):
    client.send(user_id, "hello")
    return True
