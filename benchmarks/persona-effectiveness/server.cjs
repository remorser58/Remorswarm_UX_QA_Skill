const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const port=Number(process.env.PORT||4187);
http.createServer((req,res)=>{ const route=req.url.split('?')[0]; const file=route==='/'?'index.html':route==='/app.js'?'app.js':null; if(!file){res.writeHead(404);return res.end('Not found');}res.setHeader('Content-Type',file.endsWith('js')?'text/javascript':'text/html');res.end(fs.readFileSync(path.join(__dirname,file))); }).listen(port,'127.0.0.1',()=>console.log(`Fixture http://127.0.0.1:${port}`));
