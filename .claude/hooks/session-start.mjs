// SessionStart hook: tells Claude who is working (role from .claude/role.local.json),
// the current git state, and to ask about the session's task before doing anything.
import { readFileSync, existsSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const roleFile = join(root, '.claude', 'role.local.json');
const ROLES = { FE: 'frontend', B1: 'backend + infrastruktura', B2: 'backend + baza danych', AI: 'serwis AI + backend' };

function git(cmd) {
  try {
    return execSync(`git ${cmd}`, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return '';
  }
}

let who = null;
if (existsSync(roleFile)) {
  try {
    who = JSON.parse(readFileSync(roleFile, 'utf8').replace(/^\uFEFF/, ''));
  } catch {
    who = null;
  }
}

const branch = git('branch --show-current') || '(brak)';
const changes = git('status --short').split('\n').filter(Boolean).length;
const lines = ['# Start sesji — Rate Your Ride', '',
  'Przed pracą przeczytaj .claude/skills/project-overview/SKILL.md, potem skill obszaru.',
  'Sprawdź git status i git fetch. Zaktualizuj Stan/TODO skilla i overview po zmianach.', ''];

if (who && ROLES[who.role]) {
  lines.push(`Osoba: ${who.name} (${who.role} — ${ROLES[who.role]}). Dziennik: docs/journal/${who.role}.md.`);
} else {
  lines.push(
    'Nie wiadomo, kto pracuje. ZANIM zrobisz cokolwiek innego, zapytaj przez AskUserQuestion o imię i rolę',
    '(FE — frontend, B1 — backend + infrastruktura, B2 — backend + baza danych, AI — serwis AI + backend),',
    'a potem zapisz {"name": "...", "role": "FE|B1|B2|AI"} do .claude/role.local.json (plik jest w .gitignore).',
  );
}

lines.push(
  '',
  'Przed pierwszą pracą w tej sesji zapytaj, nad czym ta osoba teraz pracuje (zadanie i gałąź),',
  'chyba że pierwsza wiadomość już to jasno mówi. Potem dodaj wpis w jej dzienniku (zasady w CLAUDE.md).',
  '',
  `Git: gałąź \`${branch}\`, niezacommitowanych zmian: ${changes}.` +
    (branch === 'main' ? ' Uwaga: to `main` — praca tylko na gałęzi z sekcji 7 planu.' : ''),
);

process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: lines.join('\n') },
  }),
);
