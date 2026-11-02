const express = require('express');
const http = require('http');
const net = require('net');

const app = express();
const port = 8080;

// Conexão TCP com FFmpeg MJPEG
const client = net.connect({ port: 8090 }, () => {
    console.log('📡 Conectado ao stream FFmpeg TCP.');
});

app.get('/stream.mjpg', (req, res) => {
    res.writeHead(200, {
        'Content-Type': 'multipart/x-mixed-replace; boundary=ffserver'
    });

    client.on('data', (chunk) => {
        res.write(chunk);
    });

    req.on('close', () => {
        console.log('⛔ Cliente desconectado.');
    });
});

app.listen(port, () => {
    console.log(`🚀 Servidor rodando em http://localhost:${port}`);
});
