const pendingMutationIds = new Map()
const MUTATION_ID_TTL_MS = 60_000

function removeExpiredMutationIds(now = Date.now()) {
  for (const [mutationId, createdAt] of pendingMutationIds) {
    if (now - createdAt > MUTATION_ID_TTL_MS) {
      pendingMutationIds.delete(mutationId)
    }
  }
}

export function createClientMutationId() {
  removeExpiredMutationIds()
  const mutationId = crypto.randomUUID()
  pendingMutationIds.set(mutationId, Date.now())
  return mutationId
}

export function isOwnMutation(mutationId) {
  if (typeof mutationId !== 'string') return false
  removeExpiredMutationIds()
  return pendingMutationIds.delete(mutationId)
}

export function clearPendingMutations() {
  pendingMutationIds.clear()
}
