// render.js — Portal SimonSports — Loterias → Imagem 1080x1080 (Opção B 3D)
// Lê data/to_publish.json, aplica templates/post-instagram.html,
// usa fundos em assets/fundos/<slug>.jpg e logos em assets/logos/<slug>.png,
// e salva as imagens finais em output/<arquivo>.jpg

import fs from 'fs';
import path from 'path';
import { pathToFileURL } from 'url';
import puppeteer from 'puppeteer';

const ROOT          = process.cwd();
const OUT_DIR       = path.join(ROOT, 'output');
const DATA_FILE     = path.join(ROOT, 'data', 'to_publish.json');
const TEMPLATE_FILE = path.join(ROOT, 'templates', 'post-instagram.html');

/* ================= Utils ================= */
function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}
function safe(v){ return (v===undefined || v===null) ? '' : String(v); }
function isHttp(u){ return /^https?:\/\//i.test(String(u||'')); }
function fileUrl(absPath){ return pathToFileURL(absPath).href; }

// remove caracteres invisíveis comuns (ZERO-WIDTH etc.)
function stripInvisible(s){
  return String(s||'').replace(/[\u200B-\u200D\uFEFF\u2060]/g, '');
}

function slugify(s){
  return stripInvisible(String(s||''))
    .toLowerCase()
    .normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
    // hífen no fim para evitar "range out of order"
    .replace(/[^a-z0-9 _-]+/g,'')
    .trim().replace(/\s+/g,'-');
}

// Nome -> slug (arquivos de fundo/logo)
const LOTERIA_SLUGS = {
  'mega-sena':'mega-sena',
  'megasena':'mega-sena',
  'mega sena':'mega-sena',

  'quina':'quina',

  'lotofacil':'lotofacil',
  'lotofácil':'lotofacil',

  'lotomania':'lotomania',

  'timemania':'timemania',

  'dupla sena':'dupla-sena',
  'dupla-sena':'dupla-sena',
  'duplasena':'dupla-sena',

  // Loteria Federal → sempre "loteria-federal"
  'federal':'loteria-federal',
  'loteria federal':'loteria-federal',
  'loteria-federal':'loteria-federal',

  'dia de sorte':'dia-de-sorte',
  'dia-de-sorte':'dia-de-sorte',
  'diadesorte':'dia-de-sorte',

  'super sete':'super-sete',
  'super-sete':'super-sete',
  'supersete':'super-sete',

  'loteca':'loteca',

  'mais-milionaria':'mais-milionaria',
  'mais milionaria':'mais-milionaria',
  'mais milionária':'mais-milionaria',
  '+milionaria':'mais-milionaria',
  '+milionária':'mais-milionaria'
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

// Normaliza números gerais (“1 2;03,4” → “01, 02, 03, 04”)
function normalizeNumerosGeneric(raw){
  let s = safe(raw).replace(/[;\|\s]+/g, ',');
  const parts = s.split(',').map(x => x.trim()).filter(Boolean);
  const norm = parts.map(p => /^\d{1,2}$/.test(p) ? ('0'+Number(p)).slice(-2) : p);
  return norm.join(', ');
}

// Preserva “ x ” / “×” da Loteca e numerações (não mexe na pontuação)
function normalizeNumerosLoteca(raw){
  return stripInvisible(String(raw||'')).trim();
}

/* ======= helpers filename (anti-dobras) ======= */
/**
 * Regras para nome de arquivo:
 *
 * 1) Se houver CONCURSO:
 *    - extrai o primeiro número do concurso
 *      ex: "Concurso 2931", "2931", "2931 (Especial)" → 2931
 *    - filename = "<slug>-<numero>.jpg"
 *      ex: mega-sena-2931.jpg
 *
 * 2) Se NÃO houver concurso mas existir id:
 *    - tenta usar o id já normalizado:
 *      a) se começar com "<slug>-": usa direto (mega-sena-2931)
 *      b) senão: "<slug>-<id-normalizado>"
 *
 * 3) Se não tiver nem concurso nem id:
 *    - tenta usar data como tag
 *    - se ainda assim não tiver nada: "<slug>.jpg"
 */
function buildFilename(loteria, concurso, data, id){
  const slug = guessSlug(loteria);

  // 1) Tentar pelo CONCURSO
  let numero = '';
  if (concurso) {
    const m = String(concurso).match(/\d+/);
    if (m) numero = m[0];
  }
  if (numero) {
    return `${slug}-${numero}.jpg`;
  }

  // 2) Sem concurso → tentar pelo ID
  const cleanId = slugify(stripInvisible(id || ''));
  if (cleanId) {
    if (cleanId.startsWith(`${slug}-`)) {
      // já está no formato mega-sena-2931, etc.
      return `${cleanId}.jpg`;
    }
    // senão, pendura o id normalizado depois do slug
    return `${slug}-${cleanId}.jpg`;
  }

  // 3) fallback com data
  const tagRaw = stripInvisible(safe(data));
  const tag = slugify(tagRaw);
  if (tag) {
    return `${slug}-${tag}.jpg`;
  }

  // 4) fallback extremo
  return `${slug}.jpg`;
}

function ensureUniquePath(dir, filename){
  let out = path.join(dir, filename);
  if (!fs.existsSync(out)) return out;
  const ext = path.extname(filename);        // .jpg
  const name = path.basename(filename, ext); // ex: quina-6875
  let i = 1;
  while (true){
    const trial = path.join(dir, `${name}-${i}${ext}`);
    if (!fs.existsSync(trial)) return trial;
    i++;
  }
}

/* =============== Build fields =============== */
function buildFields(item){
  const loteria  = safe(item.Loteria || item.Produto);
  const concurso = safe(item.Concurso);
  const data     = safe(item.Data);
  const rawNum   = item['Números'] ?? item.Numeros;
  const url      = safe(item.URL ?? item.Url);
  const tg1      = safe(item.TelegramC1 ?? item.TELEGRAM_CANAL_1);
  const tg2      = safe(item.TelegramC2 ?? item.TELEGRAM_CANAL_2);

  const slug = guessSlug(loteria);

  // Fundo e Logo — prioriza o que vier no JSON; senão usa pasta /assets
  let fundo = resolvePathOrUrl(item.ImagemFundo);
  if (!fundo) {
    const localFundo = path.join('assets','fundos', `${slug}.jpg`);
    fundo = resolvePathOrUrl(localFundo);
  }
  let logo = resolvePathOrUrl(item.Logo);
  if (!logo) {
    const localLogo = path.join('assets','logos', `${slug}.png`);
    logo = resolvePathOrUrl(localLogo);
  }

  // ===== DESCRIÇÃO =====
  let numeros = '';
  let descricao = '';
  if (slug === 'loteca') {
    numeros = normalizeNumerosLoteca(rawNum);
    descricao = '';
  } else if (slug === 'dupla-sena') {
    const n = normalizeNumerosGeneric(rawNum);
    const parts = n.split(',').map(x => x.trim()).filter(Boolean);
    if (parts.length === 12) {
      const s1 = parts.slice(0,6).join(', ');
      const s2 = parts.slice(6,12).join(', ');
      descricao = `1º sorteio: ${s1}\n2º sorteio: ${s2}`;
    } else {
      descricao = `Números: ${n}`;
    }
    numeros = n;
  } else if (slug === 'loteria-federal') {
    const clean = stripInvisible(String(rawNum||''));
    const parts = clean.split(/[,\n;]+/).map(s => s.trim()).filter(Boolean);
    if (parts.length >= 5) {
      const top5 = parts.slice(0,5);
      descricao = `1º ${top5[0]}\n2º ${top5[1]}\n3º ${top5[2]}\n4º ${top5[3]}\n5º ${top5[4]}`;
    } else {
      descricao = `Resultados: ${normalizeNumerosGeneric(rawNum)}`;
    }
    numeros = clean;
  } else {
    const n = normalizeNumerosGeneric(rawNum);
    numeros = n;
    descricao = n ? `Números: ${n}` : '';
  }

  const produto = concurso ? `${loteria} • Concurso ${concurso}` : loteria;

  // nova lógica de nome do arquivo (baseada em slug + concurso)
  const filename = buildFilename(loteria, concurso, data, item.id);

  return { slug, produto, data, descricao, url, tg1, tg2, fundo, logo, filename, numeros };
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
    .replace(/{{TelegramC2}}/g,  f.tg2)
    .replace(/{{Slug}}/g,        f.slug)
    .replace(/{{NumerosRaw}}/g,  f.numeros||'');
}

/* ================= MAIN ================= */
async function main(){
  ensureDir(OUT_DIR);

  if (!fs.existsSync(TEMPLATE_FILE)) {
    console.error('❌ Template não encontrado:', TEMPLATE_FILE);
    process.exit(1);
  }
  if (!fs.existsSync(DATA_FILE)) {
    console.log('ℹ️  Nada a renderizar:', DATA_FILE, 'não existe.');
    process.exit(0);
  }

  let items = [];
  try {
    items = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8') || '[]');
  } catch (e) {
    console.error('❌ JSON inválido em', DATA_FILE, e.message);
    process.exit(1);
  }

  if (!Array.isArray(items) || items.length === 0){
    console.log('ℹ️  Nada para gerar: data/to_publish.json está vazio.');
    return;
  }

  const template = fs.readFileSync(TEMPLATE_FILE, 'utf8');

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      defaultViewport: { width:1080, height:1080, deviceScaleFactor: 2 },
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-gpu',
        '--font-render-hinting=none',
        '--lang=pt-BR'
      ]
    });
  } catch (e) {
    console.error('❌ Falha ao iniciar o Puppeteer/Chromium:', e.message);
    process.exit(1);
  }

  const page = await browser.newPage();

  for (const item of items){
    const f = buildFields(item);

    if (!f.fundo) console.warn(`⚠️  Fundo ausente para "${f.slug}" — verifique assets/fundos/${f.slug}.jpg`);
    if (!f.logo)  console.warn(`⚠️  Logo ausente para "${f.slug}" — verifique assets/logos/${f.slug}.png`);

    const html = applyTemplate(template, f);
    await page.setContent(html, { waitUntil: 'domcontentloaded' });
    try { await page.evaluateHandle('document.fonts.ready'); } catch(_e){}

    const outPath = ensureUniquePath(OUT_DIR, f.filename);
    await page.screenshot({ path: outPath, type: 'jpeg', quality: 95 });
    console.log('✅ Imagem gerada:', outPath);
  }

  await browser.close();
}

main().catch(err => {
  console.error('❌ Erro no render:', err);
  process.exit(1);
});