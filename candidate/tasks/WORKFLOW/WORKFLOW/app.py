"""Fixed Python environment. Implement the business endpoints in this project."""
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

@app.get('/healthz')
def health():
    return {'status': 'ok'}

@app.get('/', response_class=HTMLResponse)
def home():
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>待实现</title><body>待实现</body></html>'

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8080')))
