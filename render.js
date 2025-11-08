// render.js — Portal SimonSports — Loterias -> Imagem 1080x1080 (Opção B 3D)
// Gera imagens a partir de templates HTML usando Puppeteer
// Estrutura esperada:
//   data/to_publish.json  (GAS escreve)
//   templates/post-instagram.html
//   assets/fundos/<slug>.jpg        (Opção B 3D)
//   assets/logos/<slug>.png         (logos oficiais)
// Saída: output/<slug>[-concurso|data].jpg

import fs from 'fs';
import path from 'path';
import puppeteer from 'puppeteer';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, 'output');
const DATA_FILE = path.join(ROOT, 'data', 'to_publish.json');
const TEMPLATE_FILE = path.join(ROOT, 'templates', 'post-instagram.html');

// ---- utils ---------------------------------------------------------------

function ensureDir(p){ if(!fs.existsSync(p)) fs.mkdirSync(p, { recursive:true }); }

function slugify(s){
  return String(s||'')
    .toLowerCase()
    .normalize('NFKD').replace(/[\u0300-\u036f]/g,'')   // remove acentos
    .replace(/[^a-z0-9\- ]+/g,'')                       // apenas alfa-num e espaço/hífen
    .trim().replace(/\s+/g,'-');
}

// Mapeia nome da loteria -> slug dos arquivos de fundo/logo
const LOTERIA_SLUGS = {
  'mega-sena':'mega-sena',
  'quina':'quina',
  'lotofacil':'lotofacil',
  'lotofácil':'lotofacil',
  'lotomania':'lotomania',
  'timemania':'timemania',
  'dupla sena':'dupla-sena',
  'dupla-sena':'dupla-sena',
  'federal':'federal',
  'dia de sorte':'dia-de-sorte',
  'dia-de-sorte':'dia-de-sorte',
  'super sete':'super-sete',
  'super-sete':'super-sete',
  'loteca':'loteca',
};

function guessSlug(loteriaOuProduto){
  const p = String(loteriaOuProduto||'').toLowerCase();
  for (const k of Object.keys(LOTERIA_SLUGS)){
    if (p.includes(k)) return LOTERIA_SLUGS[k];
  }
  return slugify(loteriaOuProduto||'loteria');
}

function fileUrl(relPath){ return `file://${path.join(ROOT, relPath)}`; }

function safeVal(v){ return (v===undefined || v===null) ? '' : String(v); }

function buildFields(item){
  // Campos da planilha esperados:
  // Loteria | Concurso | Data | Números | URL | (opcionais) TelegramC1 | TelegramC2 | Logo | ImagemFundo
  const loteria  = safeVal(item.Loteria || item.Produto || '');
  const concurso = safeVal(item.Concurso || '');
  const data     = safeVal(item.Data || '');
  const numeros  = safeVal(item.Números || item.Numeros || '');
  const url      = safeVal(item.URL || item.Url || '');
  const tg1      = safeVal(item.TelegramC1 || item.TELEGRAM_CANAL_1 || item.Telegram1 || '');
  const tg2      = safeVal(item.TelegramC2 || item.TELEGRAM_CANAL_2 || item.Telegram2 || '');

  const slug = guessSlug(loteria);

  // Fallbacks de imagem (Opção B 3D)
  const fundo = (item.ImagemFundo && String(item.ImagemFundo).trim())
    ? item.ImagemFundo
    : fileUrl(path.join('assets','fundos', `${slug}.jpg`));

  const logo = (item.Logo && String(item.Logo).trim())
    ? item.Logo
    : fileUrl(path.join('assets','logos', `${slug}.png`));

  // Título e descrição padrão para o template
  const produto = concurso ? `${loteria} • Concurso ${concurso}` : loteria;
  const descricao = numeros ? `Números: ${numeros}` : '';

  // Nome de arquivo
  const tag = concurso || data || '';
  const fname = tag ? `${slug}-${slugify(tag)}.jpg` : `${slug}.jpg`;

  return {
    slug, produto, data, descricao, url, tg1, tg2, fundo, logo, filename: fname
  };
}

// Substitui as chaves do template sem quebrar markup
function applyTemplate(html, fields){
  return html
    .replace(/{{ImagemFundo}}/g, fields.fundo)
    .replace(/{{Logo}}/g, fields.logo)
    .replace(/{{Produto}}/g, fields.produto)
    .replace(/{{Data}}/g, fields.data)
    .replace(/{{Descricao}}/g, fields.descricao)
    .replace(/{{URL}}/g, fields.url)
    .replace(/{{TelegramC1}}/g, fields.tg1)
    .replace(/{{TelegramC2}}/g, fields.tg2);
}

// ---- main ----------------------------------------------------------------

async function main(){
  ensureDir(OUT_DIR);

  if (!fs.existsSync(DATA_FILE)) {
    console.log('Arquivo não encontrado:', DATA_FILE);
    process.exit(0);
  }

  const raw = fs.readFileSync(DATA_FILE, 'utf8') || '[]';
  let items = [];
  try { items = JSON.parse(raw); } catch(e){ items = []; }

  if (!Array.isArray(items) || items.length === 0) {
    console.log('Nada para gerar: data/to_publish.json está vazio.');
    return;
  }

  const template = fs.readFileSync(TEMPLATE_FILE, 'utf8');
  const browser = await puppeteer.launch({
    headless: 'new',
    defaultViewport: { width:1080, height:1080, deviceScaleFactor: 2 },
    args: ['--no-sandbox','--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  for (const item of items){
    const f = buildFields(item);
    const html = applyTemplate(template, f);

    await page.setContent(html, { waitUntil: 'networkidle0' });

    const outPath = path.join(OUT_DIR, f.filename);
    await page.screenshot({ path: outPath, type: 'jpeg', quality: 95 });
    console.log('✅ Imagem gerada:', outPath);
  }

  await browser.close();
}

main().catch(err => {
  console.error('❌ Erro no render:', err);
  process.exit(1);
});
