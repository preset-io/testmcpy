import yaml from 'js-yaml'

/**
 * Convert JSON Schema to various formats for developer convenience
 */

/**
 * Resolve $ref references in JSON Schema
 * Handles both internal references (#/$defs/...) and definitions
 */
function resolveRef(ref, schema) {
  if (!ref || typeof ref !== 'string') return null

  // Handle internal references like #/$defs/TypeName or #/definitions/TypeName
  if (ref.startsWith('#/')) {
    const path = ref.substring(2).split('/')
    let current = schema

    for (const segment of path) {
      if (!current || typeof current !== 'object') return null
      current = current[segment]
    }

    return current
  }

  return null
}

/**
 * Resolve all $refs in a property recursively
 */
function resolveProperty(prop, schema) {
  if (!prop || typeof prop !== 'object') return prop

  // If this property is a $ref, resolve it
  if (prop.$ref) {
    const resolved = resolveRef(prop.$ref, schema)
    if (resolved) {
      // Merge any additional properties from the reference with the resolved definition
      const { $ref, ...rest } = prop
      return { ...resolved, ...rest }
    }
  }

  // Handle anyOf by taking the first non-null option
  if (prop.anyOf && Array.isArray(prop.anyOf)) {
    // Filter out null types and take the first valid type
    const nonNullTypes = prop.anyOf.filter(t => t.type !== 'null')
    if (nonNullTypes.length > 0) {
      // If there's a null in anyOf, make it optional
      const hasNull = prop.anyOf.some(t => t.type === 'null')
      const firstType = resolveProperty(nonNullTypes[0], schema)
      return {
        ...firstType,
        nullable: hasNull || firstType.nullable,
        ...prop  // Preserve other properties like default, description
      }
    }
  }

  // Recursively resolve nested properties
  if (prop.properties) {
    const resolvedProps = {}
    for (const [key, value] of Object.entries(prop.properties)) {
      resolvedProps[key] = resolveProperty(value, schema)
    }
    prop.properties = resolvedProps
  }

  // Resolve array items
  if (prop.items) {
    prop.items = resolveProperty(prop.items, schema)
  }

  return prop
}

/**
 * Resolve all $refs in a schema
 */
function resolveSchema(schema) {
  if (!schema || typeof schema !== 'object') return schema

  const resolved = { ...schema }

  // Resolve properties
  if (resolved.properties) {
    const resolvedProps = {}
    for (const [key, value] of Object.entries(resolved.properties)) {
      resolvedProps[key] = resolveProperty(value, schema)
    }
    resolved.properties = resolvedProps
  }

  return resolved
}

/**
 * Convert JSON Schema to formatted JSON
 */
export function toJSON(schema) {
  return JSON.stringify(schema, null, 2)
}

/**
 * Convert JSON Schema to YAML
 */
export function toYAML(schema) {
  try {
    return yaml.dump(schema, {
      indent: 2,
      lineWidth: 80,
      noRefs: true,
      sortKeys: false,
    })
  } catch (error) {
    console.error('Error converting to YAML:', error)
    return `# Error converting to YAML: ${error.message}`
  }
}

/**
 * Convert JSON Schema properties to TypeScript interface
 */
export function toTypeScript(schema, interfaceName = 'Parameters') {
  // Resolve all $refs first
  schema = resolveSchema(schema)

  if (!schema || !schema.properties) {
    return `interface ${interfaceName} {
  // No parameters defined
}`
  }

  const interfaces = []
  let nestedInterfaceCounter = 0

  const convertType = (prop, depth = 0, parentName = '') => {
    if (prop.enum) {
      return prop.enum.map(v => typeof v === 'string' ? `'${v}'` : v).join(' | ')
    }

    // Handle anyOf (union types) - already resolved by resolveProperty
    if (prop.anyOf && Array.isArray(prop.anyOf)) {
      const types = prop.anyOf
        .filter(t => t.type !== 'null')
        .map(t => convertType(t, depth, parentName))
      const hasNull = prop.anyOf.some(t => t.type === 'null')

      if (types.length === 0) return 'null'
      if (types.length === 1) return hasNull ? `${types[0]} | null` : types[0]

      const unionType = types.join(' | ')
      return hasNull ? `(${unionType}) | null` : unionType
    }

    switch (prop.type) {
      case 'string':
        return 'string'
      case 'number':
      case 'integer':
        return 'number'
      case 'boolean':
        return 'boolean'
      case 'array':
        if (prop.items) {
          const itemType = convertType(prop.items, depth, parentName)
          return `${itemType}[]`
        }
        return 'any[]'
      case 'object':
        if (prop.properties) {
          // For nested objects, create a separate interface or inline type
          if (depth === 0) {
            // Inline for first level
            const nestedLines = []
            Object.entries(prop.properties).forEach(([nestedName, nestedProp]) => {
              const nestedType = convertType(nestedProp, depth + 1, nestedName)
              const optional = !prop.required?.includes(nestedName) ? '?' : ''
              const comment = nestedProp.description ? ` // ${nestedProp.description}` : ''
              nestedLines.push(`    ${nestedName}${optional}: ${nestedType}${comment}`)
            })
            return `{\n${nestedLines.join('\n')}\n  }`
          } else {
            // Create separate interface for deeper nesting
            nestedInterfaceCounter++
            const nestedInterfaceName = parentName
              ? `${parentName.charAt(0).toUpperCase()}${parentName.slice(1)}`
              : `Nested${nestedInterfaceCounter}`

            const nestedLines = [`interface ${nestedInterfaceName} {`]
            Object.entries(prop.properties).forEach(([nestedName, nestedProp]) => {
              const nestedType = convertType(nestedProp, depth + 1, nestedName)
              const optional = !prop.required?.includes(nestedName) ? '?' : ''
              const comment = nestedProp.description ? ` // ${nestedProp.description}` : ''
              nestedLines.push(`  ${nestedName}${optional}: ${nestedType}${comment}`)
            })
            nestedLines.push('}')
            interfaces.push(nestedLines.join('\n'))

            return nestedInterfaceName
          }
        }
        return 'Record<string, any>'
      default:
        return 'any'
    }
  }

  const lines = [`interface ${interfaceName} {`]

  Object.entries(schema.properties).forEach(([name, prop]) => {
    const optional = !schema.required?.includes(name) ? '?' : ''
    const type = convertType(prop, 0, name)
    const comment = prop.description ? ` // ${prop.description}` : ''
    lines.push(`  ${name}${optional}: ${type}${comment}`)
  })

  lines.push('}')

  // Prepend nested interfaces
  if (interfaces.length > 0) {
    return interfaces.join('\n\n') + '\n\n' + lines.join('\n')
  }

  return lines.join('\n')
}

/**
 * Convert JSON Schema properties to Python TypedDict
 */
export function toPython(schema, className = 'Parameters') {
  // Resolve all $refs first
  schema = resolveSchema(schema)

  if (!schema || !schema.properties) {
    return `from typing import TypedDict

class ${className}(TypedDict):
    # No parameters defined
    pass`
  }

  const classes = []
  let nestedClassCounter = 0

  const convertType = (prop, isOptional = false, parentName = '', depth = 0) => {
    let baseType
    let alreadyOptional = false

    if (prop.enum) {
      const enumValues = prop.enum.map(v => typeof v === 'string' ? `'${v}'` : v).join(', ')
      baseType = `Union[${enumValues}]`
    } else if (prop.anyOf && Array.isArray(prop.anyOf)) {
      // Handle anyOf (union types)
      const types = prop.anyOf
        .filter(t => t.type !== 'null')
        .map(t => convertType(t, false, parentName, depth))
      const hasNull = prop.anyOf.some(t => t.type === 'null')

      if (types.length === 0) {
        baseType = 'None'
        alreadyOptional = true
      } else if (types.length === 1) {
        baseType = types[0]
        if (hasNull) {
          baseType = `Optional[${baseType}]`
          alreadyOptional = true
        }
      } else {
        baseType = `Union[${types.join(', ')}]`
        if (hasNull) {
          baseType = `Optional[${baseType}]`
          alreadyOptional = true
        }
      }
    } else {
      switch (prop.type) {
        case 'string':
          baseType = 'str'
          break
        case 'number':
        case 'integer':
          baseType = prop.type === 'integer' ? 'int' : 'float'
          break
        case 'boolean':
          baseType = 'bool'
          break
        case 'array':
          if (prop.items) {
            const itemType = convertType(prop.items, false, parentName, depth)
            baseType = `List[${itemType}]`
          } else {
            baseType = 'List[Any]'
          }
          break
        case 'object':
          if (prop.properties) {
            // Create nested TypedDict class
            nestedClassCounter++
            const nestedClassName = parentName
              ? `${parentName.charAt(0).toUpperCase()}${parentName.slice(1).replace(/[^a-zA-Z0-9_]/g, '_')}`
              : `Nested${nestedClassCounter}`

            const nestedLines = [`class ${nestedClassName}(TypedDict):`]
            Object.entries(prop.properties).forEach(([nestedName, nestedProp]) => {
              const nestedIsOptional = !prop.required?.includes(nestedName)
              const nestedType = convertType(nestedProp, nestedIsOptional, nestedName, depth + 1)
              const comment = nestedProp.description ? `  # ${nestedProp.description}` : ''
              const safeName = nestedName.replace(/[^a-zA-Z0-9_]/g, '_')
              nestedLines.push(`    ${safeName}: ${nestedType}${comment}`)
            })

            classes.push(nestedLines.join('\n'))
            baseType = nestedClassName
          } else {
            baseType = 'Dict[str, Any]'
          }
          break
        default:
          baseType = 'Any'
      }
    }

    return (isOptional && !alreadyOptional) ? `Optional[${baseType}]` : baseType
  }

  const lines = [
    'from typing import TypedDict, Optional, List, Dict, Any, Union',
    '',
  ]

  // Add nested classes first
  Object.entries(schema.properties).forEach(([name, prop]) => {
    const isOptional = !schema.required?.includes(name)
    convertType(prop, isOptional, name, 0)
  })

  if (classes.length > 0) {
    lines.push(...classes, '', '')
  }

  lines.push(`class ${className}(TypedDict):`)

  Object.entries(schema.properties).forEach(([name, prop]) => {
    const isOptional = !schema.required?.includes(name)
    // Reset for actual generation
    const type = convertType(prop, isOptional, name, 0)
    const comment = prop.description ? `  # ${prop.description}` : ''

    // Python identifiers can't have special characters
    const safeName = name.replace(/[^a-zA-Z0-9_]/g, '_')
    lines.push(`    ${safeName}: ${type}${comment}`)
  })

  return lines.join('\n')
}

/**
 * Convert JSON Schema to cURL-friendly MCP JSON-RPC request
 */
export function toCurl(schema, toolName = 'tool_name') {
  // Resolve all $refs first
  schema = resolveSchema(schema)

  const exampleArgs = generateExample(schema)

  // Create proper MCP JSON-RPC request
  const mcpRequest = {
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: {
      name: toolName,
      arguments: exampleArgs
    }
  }

  const jsonStr = JSON.stringify(mcpRequest, null, 2)

  // Generate cURL command with MCP-specific headers
  return `# MCP JSON-RPC Tool Call
# Replace \${MCP_URL} with your MCP server URL (e.g., http://localhost:8000/mcp)
# Replace \${AUTH_TOKEN} with your bearer token if authentication is required

curl -X POST \${MCP_URL} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \${AUTH_TOKEN}" \\
  -d '${jsonStr}'

# For SSE (Server-Sent Events) transport:
# Add header: -H "Accept: text/event-stream"

# For stdio transport:
# Use tool-specific client library instead of cURL`
}

/**
 * Generate example data from schema
 */
export function generateExample(schema) {
  if (!schema || !schema.properties) {
    return {}
  }

  const example = {}

  Object.entries(schema.properties).forEach(([name, prop]) => {
    // Always include required fields, include optional only if they have defaults
    const isRequired = schema.required?.includes(name)

    if (!isRequired && prop.default === undefined) {
      return
    }

    if (prop.default !== undefined) {
      example[name] = prop.default
    } else if (prop.enum && prop.enum.length > 0) {
      example[name] = prop.enum[0]
    } else if (prop.anyOf && Array.isArray(prop.anyOf)) {
      // Handle anyOf - take the first non-null type
      const nonNullTypes = prop.anyOf.filter(t => t.type !== 'null')
      if (nonNullTypes.length > 0) {
        const firstType = nonNullTypes[0]
        example[name] = generateExampleValue(firstType)
      } else {
        example[name] = null
      }
    } else {
      example[name] = generateExampleValue(prop)
    }
  })

  return example
}

/**
 * Generate example value for a property
 */
function generateExampleValue(prop) {
  if (prop.default !== undefined) return prop.default
  if (prop.enum && prop.enum.length > 0) return prop.enum[0]

  switch (prop.type) {
    case 'string':
      return prop.format === 'email' ? 'user@example.com' :
             prop.format === 'uri' ? 'https://example.com' :
             prop.example || 'string'
    case 'number':
      return prop.minimum !== undefined ? prop.minimum : prop.example || 0
    case 'integer':
      return prop.minimum !== undefined ? prop.minimum : prop.example || 0
    case 'boolean':
      return prop.example !== undefined ? prop.example : true
    case 'array':
      return prop.items ? [generateExampleValue(prop.items)] : []
    case 'object':
      return prop.properties ? generateExample(prop) : {}
    default:
      return null
  }
}

/**
 * Convert JSON Schema to Protocol Buffers (proto3)
 */
export function toProtobuf(schema, messageName = 'Parameters') {
  // Resolve all $refs first
  schema = resolveSchema(schema)

  if (!schema || !schema.properties) {
    return `syntax = "proto3";

message ${messageName} {
  // No parameters defined
}`
  }

  const messages = []
  let nestedMessageCounter = 0

  const convertType = (prop, fieldNumber, parentName = '', depth = 0) => {
    let protoType
    let isRepeated = false

    switch (prop.type) {
      case 'string':
        protoType = 'string'
        break
      case 'number':
        protoType = 'double'
        break
      case 'integer':
        protoType = prop.format === 'int64' ? 'int64' : 'int32'
        break
      case 'boolean':
        protoType = 'bool'
        break
      case 'array':
        isRepeated = true
        if (prop.items) {
          protoType = convertType(prop.items, fieldNumber, parentName, depth).type
        } else {
          protoType = 'string'
        }
        break
      case 'object':
        if (prop.properties) {
          nestedMessageCounter++
          const nestedMessageName = parentName
            ? `${parentName.charAt(0).toUpperCase()}${parentName.slice(1).replace(/[^a-zA-Z0-9_]/g, '_')}`
            : `Nested${nestedMessageCounter}`

          const nestedLines = [`message ${nestedMessageName} {`]
          let nestedFieldNum = 1
          Object.entries(prop.properties).forEach(([nestedName, nestedProp]) => {
            const { type: nestedType, repeated } = convertType(nestedProp, nestedFieldNum, nestedName, depth + 1)
            const comment = nestedProp.description ? `  // ${nestedProp.description}` : ''
            const repeatedKeyword = repeated ? 'repeated ' : ''
            nestedLines.push(`  ${repeatedKeyword}${nestedType} ${nestedName} = ${nestedFieldNum};${comment}`)
            nestedFieldNum++
          })
          nestedLines.push('}')

          messages.push(nestedLines.join('\n'))
          protoType = nestedMessageName
        } else {
          protoType = 'map<string, string>'  // Generic map for unstructured objects
        }
        break
      default:
        protoType = 'string'
    }

    return { type: protoType, repeated: isRepeated }
  }

  const lines = [
    'syntax = "proto3";',
    '',
  ]

  // Generate nested messages first
  let fieldNumber = 1
  Object.entries(schema.properties).forEach(([name, prop]) => {
    convertType(prop, fieldNumber, name, 0)
    fieldNumber++
  })

  if (messages.length > 0) {
    lines.push(...messages, '')
  }

  lines.push(`message ${messageName} {`)

  fieldNumber = 1
  Object.entries(schema.properties).forEach(([name, prop]) => {
    const { type, repeated } = convertType(prop, fieldNumber, name, 0)
    const comment = prop.description ? `  // ${prop.description}` : ''
    const repeatedKeyword = repeated ? 'repeated ' : ''
    lines.push(`  ${repeatedKeyword}${type} ${name} = ${fieldNumber};${comment}`)
    fieldNumber++
  })

  lines.push('}')

  return lines.join('\n')
}

/**
 * Convert JSON Schema to Apache Thrift IDL
 */
export function toThrift(schema, structName = 'Parameters') {
  // Resolve all $refs first
  schema = resolveSchema(schema)

  if (!schema || !schema.properties) {
    return `struct ${structName} {
  // No parameters defined
}`
  }

  const structs = []
  let nestedStructCounter = 0

  const convertType = (prop, parentName = '', depth = 0) => {
    let thriftType

    switch (prop.type) {
      case 'string':
        thriftType = 'string'
        break
      case 'number':
        thriftType = 'double'
        break
      case 'integer':
        thriftType = prop.format === 'int64' ? 'i64' : 'i32'
        break
      case 'boolean':
        thriftType = 'bool'
        break
      case 'array':
        if (prop.items) {
          const itemType = convertType(prop.items, parentName, depth)
          thriftType = `list<${itemType}>`
        } else {
          thriftType = 'list<string>'
        }
        break
      case 'object':
        if (prop.properties) {
          nestedStructCounter++
          const nestedStructName = parentName
            ? `${parentName.charAt(0).toUpperCase()}${parentName.slice(1).replace(/[^a-zA-Z0-9_]/g, '_')}`
            : `Nested${nestedStructCounter}`

          const nestedLines = [`struct ${nestedStructName} {`]
          let fieldId = 1
          Object.entries(prop.properties).forEach(([nestedName, nestedProp]) => {
            const nestedType = convertType(nestedProp, nestedName, depth + 1)
            const optional = !prop.required?.includes(nestedName) ? 'optional ' : ''
            const comment = nestedProp.description ? `  // ${nestedProp.description}` : ''
            nestedLines.push(`  ${fieldId}: ${optional}${nestedType} ${nestedName}${comment}`)
            fieldId++
          })
          nestedLines.push('}')

          structs.push(nestedLines.join('\n'))
          thriftType = nestedStructName
        } else {
          thriftType = 'map<string, string>'
        }
        break
      default:
        thriftType = 'string'
    }

    return thriftType
  }

  const lines = []

  // Generate nested structs first
  Object.entries(schema.properties).forEach(([name, prop]) => {
    convertType(prop, name, 0)
  })

  if (structs.length > 0) {
    lines.push(...structs, '')
  }

  lines.push(`struct ${structName} {`)

  let fieldId = 1
  Object.entries(schema.properties).forEach(([name, prop]) => {
    const type = convertType(prop, name, 0)
    const optional = !schema.required?.includes(name) ? 'optional ' : ''
    const comment = prop.description ? `  // ${prop.description}` : ''
    lines.push(`  ${fieldId}: ${optional}${type} ${name}${comment}`)
    fieldId++
  })

  lines.push('}')

  return lines.join('\n')
}

/**
 * Convert JSON Schema to GraphQL Input Type
 */
export function toGraphQL(schema, typeName = 'ParametersInput') {
  // Resolve all $refs first
  schema = resolveSchema(schema)

  if (!schema || !schema.properties) {
    return `input ${typeName} {
  # No parameters defined
}`
  }

  const types = []
  let nestedTypeCounter = 0

  const convertType = (prop, parentName = '', depth = 0) => {
    let graphqlType

    if (prop.enum) {
      // Create enum type
      nestedTypeCounter++
      const enumName = parentName
        ? `${parentName.charAt(0).toUpperCase()}${parentName.slice(1).replace(/[^a-zA-Z0-9_]/g, '_')}Enum`
        : `Enum${nestedTypeCounter}`

      const enumLines = [`enum ${enumName} {`]
      prop.enum.forEach(value => {
        const enumValue = typeof value === 'string'
          ? value.toUpperCase().replace(/[^A-Z0-9_]/g, '_')
          : `VALUE_${value}`
        enumLines.push(`  ${enumValue}`)
      })
      enumLines.push('}')
      types.push(enumLines.join('\n'))

      graphqlType = enumName
    } else {
      switch (prop.type) {
        case 'string':
          graphqlType = 'String'
          break
        case 'number':
          graphqlType = 'Float'
          break
        case 'integer':
          graphqlType = 'Int'
          break
        case 'boolean':
          graphqlType = 'Boolean'
          break
        case 'array':
          if (prop.items) {
            const itemType = convertType(prop.items, parentName, depth)
            graphqlType = `[${itemType}]`
          } else {
            graphqlType = '[String]'
          }
          break
        case 'object':
          if (prop.properties) {
            nestedTypeCounter++
            const nestedTypeName = parentName
              ? `${parentName.charAt(0).toUpperCase()}${parentName.slice(1).replace(/[^a-zA-Z0-9_]/g, '_')}Input`
              : `NestedInput${nestedTypeCounter}`

            const nestedLines = [`input ${nestedTypeName} {`]
            Object.entries(prop.properties).forEach(([nestedName, nestedProp]) => {
              const nestedType = convertType(nestedProp, nestedName, depth + 1)
              const required = prop.required?.includes(nestedName) ? '!' : ''
              const comment = nestedProp.description ? `  # ${nestedProp.description}` : ''
              nestedLines.push(`  ${nestedName}: ${nestedType}${required}${comment}`)
            })
            nestedLines.push('}')

            types.push(nestedLines.join('\n'))
            graphqlType = nestedTypeName
          } else {
            graphqlType = 'JSON'  // Custom scalar for unstructured objects
          }
          break
        default:
          graphqlType = 'String'
      }
    }

    return graphqlType
  }

  const lines = []

  // Generate nested types first
  Object.entries(schema.properties).forEach(([name, prop]) => {
    convertType(prop, name, 0)
  })

  if (types.length > 0) {
    lines.push(...types, '')
  }

  lines.push(`input ${typeName} {`)

  Object.entries(schema.properties).forEach(([name, prop]) => {
    const type = convertType(prop, name, 0)
    const required = schema.required?.includes(name) ? '!' : ''
    const comment = prop.description ? `  # ${prop.description}` : ''
    lines.push(`  ${name}: ${type}${required}${comment}`)
  })

  lines.push('}')

  return lines.join('\n')
}

/**
 * Placeholder for client code generators - these will call the backend API
 */
function toClientCode(language) {
  return (schema, toolName) => {
    return `// ${language} client code will be generated by the backend\n// This requires calling /api/format endpoint with format="${language}_client"`
  }
}

/**
 * Get all available formats
 */
export const FORMATS = [
  { id: 'json', label: 'JSON', language: 'json', convert: toJSON },
  { id: 'yaml', label: 'YAML', language: 'yaml', convert: toYAML },
  { id: 'typescript', label: 'TypeScript', language: 'typescript', convert: toTypeScript },
  { id: 'python', label: 'Python', language: 'python', convert: toPython },
  { id: 'protobuf', label: 'Protobuf', language: 'proto', convert: toProtobuf },
  { id: 'thrift', label: 'Thrift', language: 'java', convert: toThrift },  // Use Java syntax as closest match
  { id: 'graphql', label: 'GraphQL', language: 'graphql', convert: toGraphQL },
  { id: 'curl', label: 'cURL', language: 'shell', convert: toCurl },
  { id: 'python_client', label: 'Python Client', language: 'python', convert: toClientCode('python'), useBackend: true },
  { id: 'javascript_client', label: 'JavaScript Client', language: 'javascript', convert: toClientCode('javascript'), useBackend: true },
  { id: 'typescript_client', label: 'TypeScript Client', language: 'typescript', convert: toClientCode('typescript'), useBackend: true },
]
