package tools

import (
	"context"
	"errors"
	"log/slog"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"github.com/redpanda-data/benthos/v4/public/service"
	"gopkg.in/yaml.v3"
)

type ResourcesWrapper struct {
	svr       *server.MCPServer
	builder   *service.ResourceBuilder
	resources *service.Resources
	closeFn   func(context.Context) error
}

func NewResourcesWrapper(logger *slog.Logger, svr *server.MCPServer) *ResourcesWrapper {
	w := &ResourcesWrapper{
		svr:     svr,
		builder: service.NewResourceBuilder(),
	}
	w.builder.SetLogger(logger)
	// TODO: Add metrics
	return w
}

func (w *ResourcesWrapper) Build() (err error) {
	w.resources, w.closeFn, err = w.builder.Build()
	return
}

func (w *ResourcesWrapper) Close(ctx context.Context) error {
	closeFn := w.closeFn
	if closeFn == nil {
		return nil
	}
	w.resources = nil
	w.closeFn = nil
	return closeFn(ctx)
}

type mcpConfig struct {
	Name string `yaml:"name"`
}

type meta struct {
	MCP mcpConfig `yaml:"mcp"`
}

type resFile struct {
	Label string `yaml:"label"`
	Meta  meta   `yaml:"meta"`
}

func (w *ResourcesWrapper) AddCache(fileBytes []byte) error {
	var res resFile
	if err := yaml.Unmarshal(fileBytes, &res); err != nil {
		return err
	}

	if err := w.builder.AddCacheYAML(string(fileBytes)); err != nil {
		return err
	}

	w.svr.AddTool(mcp.NewTool("get "+res.Meta.MCP.Name,
		mcp.WithDescription("Obtain an item from the "+res.Meta.MCP.Name+" cache."),
		mcp.WithString("key",
			mcp.Description("The key of the item to obtain."),
			mcp.Required(),
		),
	), func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		key, exists := request.Params.Arguments["key"].(string)
		if !exists {
			return nil, errors.New("missing key [string] argument")
		}

		var value []byte
		var getErr error
		if err := w.resources.AccessCache(ctx, res.Label, func(c service.Cache) {
			value, getErr = c.Get(ctx, key)
		}); err != nil {
			return nil, err
		}
		if getErr != nil {
			return nil, getErr
		}

		return &mcp.CallToolResult{
			Content: []mcp.Content{
				mcp.TextContent{
					Type: "text",
					Text: string(value),
				},
			},
		}, nil
	})

	w.svr.AddTool(mcp.NewTool("set "+res.Meta.MCP.Name,
		mcp.WithDescription("Set an item within the "+res.Meta.MCP.Name+" cache."),
		mcp.WithString("key",
			mcp.Description("The key of the item to set."),
			mcp.Required(),
		),
		mcp.WithString("value",
			mcp.Description("The value of the item to set."),
			mcp.Required(),
		),
	), func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		key, exists := request.Params.Arguments["key"].(string)
		if !exists {
			return nil, errors.New("missing key [string] argument")
		}

		value, exists := request.Params.Arguments["value"].(string)
		if !exists {
			return nil, errors.New("missing value [string] argument")
		}

		var setErr error
		if err := w.resources.AccessCache(ctx, res.Label, func(c service.Cache) {
			setErr = c.Set(ctx, key, []byte(value), nil)
		}); err != nil {
			return nil, err
		}
		if setErr != nil {
			return nil, setErr
		}

		return &mcp.CallToolResult{}, nil
	})

	return nil
}
