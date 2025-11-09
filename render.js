// render.js — Portal SimonSports — Loterias → Imagem 1080x1080 (Opção B 3D)
// Lê data/to_publish.json, aplica templates/post-instagram.html,
// usa fundos em assets/fundos/<slug>.jpg e logos em assets/logos/<slug>.png,
// e salva as imagens finais em output/<arquivo>.jpg

import fs from 'fs';
import path from 'path';
import puppeteer from 'puppeteer';

const ROOT          = process.cwd();
const OUT_DIR       = path.join(ROOT, 'output');
const DATA_FILE     = path.join(ROOT, 'data', 'to_publish.json');
const TEMPLATE_FILE = path.join(ROOT, 'templates', 'post-instagram.html');

/* ================= Utils ================= */
function ensureDir(p){ if(!fs.existsSync(p)) fs.mkdirSync(p, { recursive:true }); }
function safe(v){ return (v===undefined || v===null) ? '' : String(v); }
function isHttp(u){ return /^https?:\/\//i.test(String(u||'')); }
function fileUrl(absPath){ return `file://${absPath}`; }

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
  'loteca':'loteca'
};

function guessSlug(text){
  const p = String(text||'').toLowerCase();
  for (const k of Object.keys(LOTERIA_SLUGS)){
    if (p.includes(k)) return LOTERIA_SLUGS[k];
  }
  return slugify(text||'loteria');
}

/** Converte caminho relativo para file:// absoluto.
 * Se já for http(s), retorna como está.
 * Se o arquivo local não existir, retorna null (para cair no fallback). */
function resolvePathOrUrl(relOrUrl){
  const v = String(relOrUrl||'').trim();
  if (!v) return null;
  if (isHttp(v)) return v;
  const abs = path.isAbsolute(v) ? v : path.join(ROOT, v);
  return fs.existsSync(abs) ? fileUrl(abs) : null;
}

// Normaliza números (“1 2;03,4” → “01, 02, 03, 04”)
function normalizeNumeros(raw){
  let s = safe(raw).replace(/[;\|\s]+/g, ',');
  const parts = s.split(',').map(x => x.trim()).filter(Boolean);
  const norm = parts.map(p => {
    const n = p.replace(/\D/g,'');
    if (n.length>=1 && n.length<=2) return ('0'+Number(n)).slice(-2);
    return p; // preserva “1x2” (Loteca)
  });
  return norm.join(', ');
}

/* =============== Build fields =============== */
function buildFields(item){
  // Esperado (vindo do GAS): Produto/Loteria, Concurso, Data, Números, URL, TelegramC1, TelegramC2
  const loteria  = safe(item.Loteria || item.Produto);
  const concurso = safe(item.Concurso);
  const data     = safe(item.Data);
  const numeros  = normalizeNumeros(item['Números'] ?? item.Numeros);
  const url      = safe(item.URL ?? item.Url);
  const tg1      = safe(item.TelegramC1 ?? item.TELEGRAM_CANAL_1);
  const tg2      = safe(item.TelegramC2 ?? item.TELEGRAM_CANAL_2);

  const slug = guessSlug(loteria);

  // Fundo e Logo — prioriza o que vier no JSON; senão usa pasta /assets
  let fundo = resolvePathOrUrl(item.ImagemFundo);
  if (!fundo) {
    const localFundo = path.join('assets','fundos', `${slug}.jpg`);
    fundo = resolvePathOrUrl(localFundo); // file://...
  }
  let logo = resolvePathOrUrl(item.Logo);
  if (!logo) {
    const localLogo = path.join('assets','logos', `${slug}.png`);
    logo = resolvePathOrUrl(localLogo);
  }

  // Título e descrição para o template
  const produto   = concurso ? `${loteria} • Concurso ${concurso}` : loteria;
  const descricao = numeros ? `Números: ${numeros}` : '';

  // ===== Nome do arquivo final (elimina repetições) =====
  // Preferimos 'id' quando existir (ex.: "lotomania-2846").
  // Se o 'id' já contiver o slug, não repetimos.
  const tagRaw = safe(item.id) || (concurso || data || '');
  const tag = slugify(tagRaw);
  let filename;
  if (!tag) {
    filename = `${slug}.jpg`;
  } else if (tag.startsWith(`${slug}-`)) {
    // id já contém o slug: "mega-sena-2938" → mega-sena-2938.jpg
    filename = `${tag}.jpg`;
  } else {
    filename = `${slug}-${tag}.jpg`;
  }

  return { slug, produto, data, descricao, url, tg1, tg2, fundo, logo, filename };
}

function applyTemplate(html, f){
  return html
    .replace(/{{ImagemFundo}}/g, f.fundo || '')
    .replace(/{{Logo}}/g,        f.logo || '')
    .replace(/{{Produto}}/g,     f.produto)
    .replace(/{{Data}}/g,        f.data)
    .replace(/{{Descricao}}/g,   f.descricao)
    .replace(/{{URL}}/g,         f.url)
    .replace(/{{TelegramC1}}/g,  f.tg1)
    .replace(/{{TelegramC2}}/g,  f.tg2);
}

/* ================= MAIN ================= */
async function main(){
  ensureDir(OUT_DIR);

  if (!fs.existsSync(TEMPLATE_FILE)) {
    console.error('❌ Template não encontrado:', TEMPLATE_FILE);
    process.exit(1);
  }
  if (!fs.existsSync(DATA_FILE)) {
    console.log('⚠️  Arquivo não encontrado (nada a fazer):', DATA_FILE);
    process.exit(0);
  }

  let items = [];
  try { items = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8') || '[]'); }
  catch (e) {
    console.error('❌ JSON inválido em', DATA_FILE, e.message);
    process.exit(1);
  }

  if (!Array.isArray(items) || items.length === 0){
    console.log('ℹ️  Nada para gerar: data/to_publish.json está vazio.');
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

    if (!f.fundo) console.warn(`⚠️  Fundo ausente para "${f.slug}" — verifique assets/fundos/${f.slug}.jpg`);
    if (!f.logo)  console.warn(`⚠️  Logo ausente para "${f.slug}" — verifique assets/logos/${f.slug}.png`);

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
```0