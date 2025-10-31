import React from 'react'

/**
 * Visual type indicator with icon and color coding
 * Shows parameter type with appropriate icon and color scheme
 */
function TypeBadge({ type, items, enumValues }) {
  const getTypeConfig = () => {
    switch (type) {
      case 'string':
        return {
          icon: 'Abc',
          color: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
          label: 'string'
        }
      case 'number':
      case 'integer':
        return {
          icon: '123',
          color: 'bg-green-500/10 text-green-400 border-green-500/20',
          label: type
        }
      case 'boolean':
        return {
          icon: '⊤⊥',
          color: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
          label: 'boolean'
        }
      case 'array':
        return {
          icon: '[]',
          color: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
          label: items ? `array<${items}>` : 'array'
        }
      case 'object':
        return {
          icon: '{}',
          color: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
          label: 'object'
        }
      default:
        return {
          icon: '?',
          color: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
          label: type || 'any'
        }
    }
  }

  const config = getTypeConfig()

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${config.color}`}>
      <span className="font-mono mr-1.5">{config.icon}</span>
      <span>{config.label}</span>
      {enumValues && enumValues.length > 0 && (
        <span className="ml-1 opacity-70">({enumValues.length} options)</span>
      )}
    </span>
  )
}

export default TypeBadge
