import { describe, expect, it } from 'vitest'
import { formatActivityText, relativeTime } from './activityUtils'

describe('activityUtils', () => {
  describe('relativeTime', () => {
    it('returns empty string for null, undefined, or empty values', () => {
      expect(relativeTime(null)).toBe('')
      expect(relativeTime(undefined)).toBe('')
      expect(relativeTime('')).toBe('')
      expect(relativeTime('invalid-date')).toBe('')
    })

    it('returns relative string for valid past dates', () => {
      const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
      expect(relativeTime(fiveMinutesAgo)).toMatch(/minute/)
    })
  })

  describe('formatActivityText', () => {
    it('formats project.created', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'project.created',
        }),
      ).toBe('Alice created the project')
    })

    it('formats project.updated', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'project.updated',
        }),
      ).toBe('Alice updated project settings')
    })

    it('formats member.added', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'member.added',
          details: { member_username: 'Bob', role: 'admin' },
        }),
      ).toBe('Alice added Bob as admin')
    })

    it('formats member.role_changed', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'member.role_changed',
          details: { member_username: 'Bob', new_role: 'member' },
        }),
      ).toBe('Alice changed Bob’s role to member')
    })

    it('formats member.removed', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'member.removed',
          details: { member_username: 'Bob' },
        }),
      ).toBe('Alice removed Bob from the project')
    })

    it('formats task.created', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.created',
          details: { title: 'Fix bug' },
        }),
      ).toBe('Alice created “Fix bug”')
    })

    it('formats task.updated', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.updated',
          details: { title: 'Fix bug', priority: { old: 'low', new: 'high' } },
        }),
      ).toBe('Alice updated priority on “Fix bug”')
    })

    it('formats task.moved', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.moved',
          details: { title: 'Fix bug', to_status: 'in_progress' },
        }),
      ).toBe('Alice moved “Fix bug” to in progress')
    })

    it('formats task.deleted', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.deleted',
          details: { title: 'Fix bug' },
        }),
      ).toBe('Alice deleted “Fix bug”')
    })

    it('formats comment.created', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'comment.created',
          details: { task_title: 'Fix bug' },
        }),
      ).toBe('Alice commented on “Fix bug”')
    })

    it('formats task unassigned and reviewer removal', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.unassigned',
          details: { title: 'Fix bug' },
        }),
      ).toBe('Alice unassigned “Fix bug”')

      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.reviewer_removed',
          details: { title: 'Fix bug' },
        }),
      ).toBe('Alice removed reviewer from “Fix bug”')

      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'task.completion_credit_removed',
          details: { title: 'Fix bug' },
        }),
      ).toBe('Alice adjusted completion credit on “Fix bug”')
    })

    it('falls back gracefully on unknown action', () => {
      expect(
        formatActivityText({
          actor: { username: 'Alice' },
          action: 'custom.action',
        }),
      ).toBe('Alice performed custom action')
    })
  })
})

