import { io } from 'socket.io-client'

let socket
let latestToken = null

function socketUrl() {
  return import.meta.env.VITE_SOCKET_URL || 'http://localhost:8000'
}

export function connectRealtimeSocket(token) {
  latestToken = token
  if (!socket) {
    socket = io(socketUrl(), {
      autoConnect: false,
      auth: (callback) => callback({ token: latestToken }),
    })
  }
  if (!socket.connected && !socket.active) {
    socket.connect()
  }
  return socket
}

export function getRealtimeSocket() {
  return socket
}

export function disconnectRealtimeSocket() {
  latestToken = null
  if (socket) {
    socket.disconnect()
    socket = null
  }
}
