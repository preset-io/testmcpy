import { toJSON, toYAML, toTypeScript, toPython, toCurl, generateExample } from '../formatConverters'

describe('formatConverters', () => {
  const testSchema = {
    type: 'object',
    properties: {
      name: {
        type: 'string',
        description: 'User name',
      },
      age: {
        type: 'integer',
        minimum: 0,
        maximum: 120,
      },
      email: {
        type: 'string',
        format: 'email',
      },
      role: {
        type: 'string',
        enum: ['admin', 'user', 'guest'],
      },
      tags: {
        type: 'array',
        items: {
          type: 'string',
        },
      },
      metadata: {
        type: 'object',
        properties: {
          created: {
            type: 'string',
            format: 'date-time',
          },
        },
      },
    },
    required: ['name', 'email'],
  }

  describe('toJSON', () => {
    it('should convert schema to formatted JSON', () => {
      const result = toJSON(testSchema)
      expect(result).toContain('"type": "object"')
      expect(result).toContain('"properties"')
      expect(JSON.parse(result)).toEqual(testSchema)
    })
  })

  describe('toYAML', () => {
    it('should convert schema to YAML format', () => {
      const result = toYAML(testSchema)
      expect(result).toContain('type: object')
      expect(result).toContain('properties:')
      expect(result).toContain('name:')
      expect(result).toContain('description: User name')
    })

    it('should handle errors gracefully', () => {
      const result = toYAML(undefined)
      expect(result).toContain('Error converting to YAML')
    })
  })

  describe('toTypeScript', () => {
    it('should convert schema to TypeScript interface', () => {
      const result = toTypeScript(testSchema, 'TestParams')
      expect(result).toContain('interface TestParams {')
      expect(result).toContain('name: string')
      expect(result).toContain('age?: number')
      expect(result).toContain('email: string')
      expect(result).toContain("role?: 'admin' | 'user' | 'guest'")
      expect(result).toContain('tags?: string[]')
      expect(result).toContain('metadata?: {')
    })

    it('should handle schema without properties', () => {
      const result = toTypeScript({ type: 'object' })
      expect(result).toContain('// No parameters defined')
    })

    it('should mark required fields correctly', () => {
      const result = toTypeScript(testSchema)
      // Required fields should not have '?'
      expect(result).toMatch(/name: string/)
      expect(result).toMatch(/email: string/)
      // Optional fields should have '?'
      expect(result).toMatch(/age\?: number/)
      expect(result).toMatch(/role\?: /)
    })
  })

  describe('toPython', () => {
    it('should convert schema to Python TypedDict', () => {
      const result = toPython(testSchema, 'TestParams')
      expect(result).toContain('from typing import')
      expect(result).toContain('class TestParams(TypedDict):')
      expect(result).toContain('name: str')
      expect(result).toContain('age: Optional[int]')
      expect(result).toContain('email: str')
      expect(result).toContain('tags: Optional[List[str]]')
    })

    it('should handle schema without properties', () => {
      const result = toPython({ type: 'object' })
      expect(result).toContain('# No parameters defined')
      expect(result).toContain('pass')
    })

    it('should sanitize invalid Python identifiers', () => {
      const schemaWithSpecialChars = {
        type: 'object',
        properties: {
          'user-name': { type: 'string' },
          'email.address': { type: 'string' },
        },
      }
      const result = toPython(schemaWithSpecialChars)
      expect(result).toContain('user_name:')
      expect(result).toContain('email_address:')
    })
  })

  describe('toCurl', () => {
    it('should generate cURL command with example data', () => {
      const result = toCurl(testSchema, 'test_tool')
      expect(result).toContain('curl -X POST')
      expect(result).toContain('https://api.example.com/tools/test_tool')
      expect(result).toContain('-H "Content-Type: application/json"')
      expect(result).toContain('-d')
    })
  })

  describe('generateExample', () => {
    it('should generate example data for required fields', () => {
      const result = generateExample(testSchema)
      expect(result).toHaveProperty('name')
      expect(result).toHaveProperty('email')
      expect(result.email).toBe('user@example.com')
    })

    it('should use default values when provided', () => {
      const schemaWithDefaults = {
        type: 'object',
        properties: {
          count: { type: 'integer', default: 10 },
          active: { type: 'boolean', default: true },
        },
        required: ['count'],
      }
      const result = generateExample(schemaWithDefaults)
      expect(result.count).toBe(10)
      expect(result.active).toBe(true)
    })

    it('should use first enum value', () => {
      const result = generateExample(testSchema)
      if (result.role) {
        expect(result.role).toBe('admin')
      }
    })

    it('should handle empty schema', () => {
      const result = generateExample({ type: 'object' })
      expect(result).toEqual({})
    })
  })
})