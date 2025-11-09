// render.js — Portal SimonSports — Loterias -> Imagem 1080x1080 (Opção B 3D)
// Lê data/to_publish.json, aplica templates/post-instagram.html,
// usa fundos em assets/fundos/<slug>.jpg e logos em assets/logos/<slug>.png,
// e salva as imagens finais em output/<arquivo>.jpg

import fs from 'fs';
import path from 'path';
import puppeteer from 'puppeteer';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, 'output');
const DATA_FILE = path.join(ROOT, 'data', 'to_publish.json');
const TEMPLATE_FILE = path.join(ROOT, 'templates', 'post-instagram.html');

// -------------------- utils --------------------
function ensureDir(p){ if(!fs.existsSync(p)) fs.mkdirSync(p, { recursive:true }); }
function safe(v){ return (v===undefined || v===null) ? '' : String(v); }
function slugify(s){
  return String(s||'')
    .toLowerCase()
    .normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
    .replace(/[^a-z0-9\- ]+/g,'')
    .trim().replace(/\s+/g,'-');
}

// Nome -> slug (arquivos de fundo/logo)
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
function guessSlug(text){
  const p = String(text||'').toLowerCase();
  for (const k of Object.keys(LOTERIA_SLUGS)){
    if (p.includes(k)) return LOTERIA_SLUGS[k];
  }
  return slugify(text||'loteria');
}
function fileUrl(rel){ return `file://${path.join(ROOT, rel)}`; }

function buildFields(item){
  // Esperado no JSON (GAS):
  // Loteria | Concurso | Data | Números | URL | TelegramC1 | TelegramC2 | (opcionais) Logo | ImagemFundo
  const loteria  = safe(item.Loteria || item.Produto);
  const concurso = safe(item.Concurso);
  const data     = safe(item.Data);
  const numeros  = safe(item['Números'] ?? item.Numeros);
  const url      = safe(item.URL ?? item.Url);
  const tg1      = safe(item.TelegramC1 ?? item.TELEGRAM_CANAL_1);
  const tg2      = safe(item.TelegramC2 ?? item.TELEGRAM_CANAL_2);

  const slug = guessSlug(loteria);

  // FallBacks (usa seus arquivos locais)
  const fundo = (item.ImagemFundo && String(item.ImagemFundo).trim())
    ? item.ImagemFundo
    : fileUrl(path.join('assets','fundos', `${slug}.jpg`));

  const logo = (item.Logo && String(item.Logo).trim())
    ? item.Logo
    : fileUrl(path.join('assets','logos', `${slug}.png`));

  // Título e descrição para o template
  const produto   = concurso ? `${loteria} • Concurso ${concurso}` : loteria;
  const descricao = numeros ? `Números: ${numeros}` : '';

  // Nome do arquivo final
  const tag = concurso || data || '';
  const filename = tag ? `${slug}-${slugify(tag)}.jpg` : `${slug}.jpg`;

  return { slug, produto, data, descricao, url, tg1, tg2, fundo, logo, filename };
}

function applyTemplate(html, f){
  return html
    .replace(/{{ImagemFundo}}/g, f.fundo)
    .replace(/{{Logo}}/g,        f.logo)
    .replace(/{{Produto}}/g,     f.produto)
    .replace(/{{Data}}/g,        f.data)
    .replace(/{{Descricao}}/g,   f.descricao)
    .replace(/{{URL}}/g,         f.url)
    .replace(/{{TelegramC1}}/g,  f.tg1)
    .replace(/{{TelegramC2}}/g,  f.tg2);
}

// -------------------- main --------------------
async function main(){
  ensureDir(OUT_DIR);

  if (!fs.existsSync(DATA_FILE)) {
    console.log('Arquivo não encontrado:', DATA_FILE);
    process.exit(0);
  }

  let items = [];
  try { items = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8') || '[]'); }
  catch { items = []; }

  if (!Array.isArray(items) || items.length === 0){
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
