export function referenceSignature(text: string) {
  return text.normalize('NFKC').toLocaleLowerCase('uk-UA').replace(/[’ʼ‘`]/g, "'")
    .match(/[\p{L}\p{N}]+(?:'[\p{L}\p{N}]+)*/gu)?.join(' ') ?? ''
}

export function hasTwoDistinctReferences(references: { text: string }[]) {
  return references.length >= 2 && references.every(item => item.text.trim().length >= 5)
    && new Set(references.map(item => referenceSignature(item.text))).size === references.length
}
