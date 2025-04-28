const express = require('express');
const path = require('path');

const app = express();
const port = 3000;

// Página HTML
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'html_server2.html'));
});

app.listen(port, () => {
  console.log(`🚀 Servidor 2 rodando em http://localhost:${port}`);
});
