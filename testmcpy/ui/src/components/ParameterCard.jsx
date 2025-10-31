import React, { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import TypeBadge from './TypeBadge'

/**
 * Smart parameter display with type visualization
 * Handles nested objects, arrays, enums, and all parameter metadata
 */
function ParameterCard({
  name,
  type,
  required = false,
  description,
  default: defaultValue,
  enum: enumValues,
  items,
  properties,
  minimum,
  maximum,
  pattern,
  format,
  minLength,
  maxLength,
  minItems,
  maxItems,
  depth = 0
}) {
  const [expanded, setExpanded] = useState(false)

  const hasNested = (type === 'object' && properties) || (type === 'array' && items?.properties)
  const isExpandable = hasNested || (type === 'array' && items?.type === 'object')

  return (
    <div className="space-y-2">
      <div className={`bg-surface-elevated border border-border rounded-lg p-3 hover:border-border-subtle transition-colors ${depth > 0 ? 'ml-4 border-l-2 border-l-primary/30' : ''}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {isExpandable && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="flex-shrink-0 hover:bg-surface-hover rounded p-0.5 transition-colors"
                >
                  {expanded ? (
                    <ChevronDown size={16} className="text-text-secondary" />
                  ) : (
                    <ChevronRight size={16} className="text-text-secondary" />
                  )}
                </button>
              )}
              <span className="font-mono text-sm font-medium text-primary-light">
                {name}
              </span>
              <TypeBadge
                type={type}
                items={items?.type}
                enumValues={enumValues}
              />
              {required && (
                <span className="badge badge-error text-[10px]">
                  required
                </span>
              )}
            </div>

            {description && (
              <p className="text-sm text-text-secondary mt-2 leading-relaxed">
                {description}
              </p>
            )}

            {/* Default value */}
            {defaultValue !== undefined && defaultValue !== null && (
              <div className="text-xs text-text-tertiary mt-2 flex items-center gap-1.5">
                <span className="opacity-70">Default:</span>
                <code className="font-mono bg-surface px-1.5 py-0.5 rounded border border-border">
                  {typeof defaultValue === 'object' ? JSON.stringify(defaultValue) : String(defaultValue)}
                </code>
              </div>
            )}

            {/* Enum values */}
            {enumValues && enumValues.length > 0 && (
              <div className="text-xs text-text-tertiary mt-2">
                <span className="opacity-70">Options:</span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {enumValues.map((value, idx) => (
                    <code
                      key={idx}
                      className="font-mono bg-surface px-1.5 py-0.5 rounded border border-border text-text-secondary"
                    >
                      {String(value)}
                    </code>
                  ))}
                </div>
              </div>
            )}

            {/* Constraints */}
            <div className="flex flex-wrap gap-3 mt-2 text-xs text-text-tertiary">
              {minimum !== undefined && (
                <span className="opacity-70">min: <code className="font-mono">{minimum}</code></span>
              )}
              {maximum !== undefined && (
                <span className="opacity-70">max: <code className="font-mono">{maximum}</code></span>
              )}
              {minLength !== undefined && (
                <span className="opacity-70">minLength: <code className="font-mono">{minLength}</code></span>
              )}
              {maxLength !== undefined && (
                <span className="opacity-70">maxLength: <code className="font-mono">{maxLength}</code></span>
              )}
              {minItems !== undefined && (
                <span className="opacity-70">minItems: <code className="font-mono">{minItems}</code></span>
              )}
              {maxItems !== undefined && (
                <span className="opacity-70">maxItems: <code className="font-mono">{maxItems}</code></span>
              )}
              {pattern && (
                <span className="opacity-70">pattern: <code className="font-mono text-[10px]">{pattern}</code></span>
              )}
              {format && (
                <span className="opacity-70">format: <code className="font-mono">{format}</code></span>
              )}
            </div>

            {/* Array item type info (non-object) */}
            {type === 'array' && items && !items.properties && (
              <div className="text-xs text-text-tertiary mt-2 flex items-center gap-1.5">
                <span className="opacity-70">Items:</span>
                <TypeBadge type={items.type} />
                {items.description && (
                  <span className="text-text-disabled">- {items.description}</span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Nested object properties */}
        {expanded && type === 'object' && properties && (
          <div className="mt-3 pt-3 border-t border-border space-y-2">
            {Object.entries(properties).map(([propName, propInfo]) => (
              <ParameterCard
                key={propName}
                name={propName}
                type={propInfo.type}
                required={propInfo.required}
                description={propInfo.description}
                default={propInfo.default}
                enum={propInfo.enum}
                items={propInfo.items}
                properties={propInfo.properties}
                minimum={propInfo.minimum}
                maximum={propInfo.maximum}
                pattern={propInfo.pattern}
                format={propInfo.format}
                minLength={propInfo.minLength}
                maxLength={propInfo.maxLength}
                minItems={propInfo.minItems}
                maxItems={propInfo.maxItems}
                depth={depth + 1}
              />
            ))}
          </div>
        )}

        {/* Nested array of objects */}
        {expanded && type === 'array' && items?.properties && (
          <div className="mt-3 pt-3 border-t border-border">
            <div className="text-xs font-semibold text-text-secondary mb-2">Array Item Schema:</div>
            <div className="space-y-2">
              {Object.entries(items.properties).map(([propName, propInfo]) => (
                <ParameterCard
                  key={propName}
                  name={propName}
                  type={propInfo.type}
                  required={items.required?.includes(propName)}
                  description={propInfo.description}
                  default={propInfo.default}
                  enum={propInfo.enum}
                  items={propInfo.items}
                  properties={propInfo.properties}
                  minimum={propInfo.minimum}
                  maximum={propInfo.maximum}
                  pattern={propInfo.pattern}
                  format={propInfo.format}
                  minLength={propInfo.minLength}
                  maxLength={propInfo.maxLength}
                  minItems={propInfo.minItems}
                  maxItems={propInfo.maxItems}
                  depth={depth + 1}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default ParameterCard
