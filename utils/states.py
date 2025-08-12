class State:
    def __init__(self):
        self._is_armed = False
        self._is_server_up = True

    def is_armed(self):
        return self._is_armed

    def set_armed(self, value: bool):
        self._is_armed = value

    def is_server_up(self):
        return self._is_server_up

    def set_server_up(self, value: bool):
        self._is_server_up = value

state = State()