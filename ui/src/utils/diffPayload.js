export function buildDiffPayload(patch = '') {
  const text = patch || '';
  if (!text) {
    return {
      raw_patch: '',
      files: [],
      stats: {
        files_changed: 0,
        additions: 0,
        deletions: 0,
        lines_changed: 0,
      },
      lines: [],
    };
  }
  const files = [];
  const lines = [];
  let currentFile = null;
  let additions = 0;
  let deletions = 0;

  text.split('\n').forEach((raw) => {
    if (raw.startsWith('+++ b/')) {
      currentFile = raw.slice(6);
      if (!files.some((item) => item.path === currentFile)) {
        files.push({ path: currentFile });
      }
      lines.push({ type: 'meta', content: raw, path: currentFile });
      return;
    }
    if (raw.startsWith('--- a/')) {
      lines.push({ type: 'meta', content: raw, path: currentFile });
      return;
    }
    if (raw.startsWith('@@') || raw.startsWith('diff --git')) {
      lines.push({ type: 'meta', content: raw, path: currentFile });
      return;
    }
    if (raw.startsWith('+') && !raw.startsWith('+++')) {
      additions += 1;
      lines.push({ type: 'add', content: raw.slice(1), path: currentFile });
      return;
    }
    if (raw.startsWith('-') && !raw.startsWith('---')) {
      deletions += 1;
      lines.push({ type: 'remove', content: raw.slice(1), path: currentFile });
      return;
    }
    lines.push({ type: 'context', content: raw, path: currentFile });
  });

  return {
    raw_patch: text,
    files,
    stats: {
      files_changed: files.length,
      additions,
      deletions,
      lines_changed: additions + deletions,
    },
    lines,
  };
}
