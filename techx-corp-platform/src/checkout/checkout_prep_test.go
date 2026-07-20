package main

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "github.com/open-telemetry/techx-corp/src/checkout/genproto/oteldemo"
)

type productClient struct {
	get func(context.Context, string) (*pb.Product, error)
}

func (c productClient) ListProducts(context.Context, *pb.Empty, ...grpc.CallOption) (*pb.ListProductsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}
func (c productClient) GetProduct(ctx context.Context, req *pb.GetProductRequest, _ ...grpc.CallOption) (*pb.Product, error) {
	return c.get(ctx, req.GetId())
}
func (c productClient) SearchProducts(context.Context, *pb.SearchProductsRequest, ...grpc.CallOption) (*pb.SearchProductsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}

type currencyClient struct {
	convert func(context.Context, *pb.CurrencyConversionRequest) (*pb.Money, error)
}

func (c currencyClient) GetSupportedCurrencies(context.Context, *pb.Empty, ...grpc.CallOption) (*pb.GetSupportedCurrenciesResponse, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}
func (c currencyClient) Convert(ctx context.Context, req *pb.CurrencyConversionRequest, _ ...grpc.CallOption) (*pb.Money, error) {
	return c.convert(ctx, req)
}

func usd(units int64, nanos int32) *pb.Money {
	return &pb.Money{CurrencyCode: "USD", Units: units, Nanos: nanos}
}

func cartItems(ids ...string) []*pb.CartItem {
	items := make([]*pb.CartItem, len(ids))
	for i, id := range ids {
		items[i] = &pb.CartItem{ProductId: id, Quantity: 1}
	}
	return items
}

func TestPrepOrderItemsPreservesOrderAndConcurrentlyConverts(t *testing.T) {
	var mu sync.Mutex
	var productCalls, convertCalls int
	cs := &checkout{
		productCatalogSvcClient: productClient{get: func(ctx context.Context, id string) (*pb.Product, error) {
			mu.Lock()
			productCalls++
			mu.Unlock()
			if id == "first" {
				time.Sleep(20 * time.Millisecond)
			}
			return &pb.Product{Id: id, PriceUsd: usd(map[string]int64{"first": 1, "second": 2, "third": 3}[id], 0)}, nil
		}},
		currencySvcClient: currencyClient{
			convert: func(ctx context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
				mu.Lock()
				convertCalls++
				mu.Unlock()
				units := req.GetFrom().GetUnits() * 10
				return &pb.Money{CurrencyCode: "EUR", Units: units}, nil
			},
		},
	}

	items := cartItems("first", "second", "third")
	got, err := cs.prepOrderItems(context.Background(), items, "EUR")
	if err != nil {
		t.Fatal(err)
	}
	if productCalls != 3 || convertCalls != 3 {
		t.Fatalf("productCalls=%d convertCalls=%d, want both to be 3", productCalls, convertCalls)
	}
	for i, want := range []int64{1, 2, 3} {
		if got[i].GetItem() != items[i] || got[i].GetCost().GetUnits() != (want*10) {
			t.Fatalf("index %d was not preserved: item=%v cost=%v", i, got[i].GetItem(), got[i].GetCost())
		}
	}
}

func TestPrepOrderItemsBoundsConcurrency(t *testing.T) {
	var mu sync.Mutex
	active, maxActive := 0, 0
	cs := &checkout{
		productCatalogSvcClient: productClient{get: func(ctx context.Context, id string) (*pb.Product, error) {
			mu.Lock()
			active++
			if active > maxActive {
				maxActive = active
			}
			mu.Unlock()
			select {
			case <-time.After(15 * time.Millisecond):
			case <-ctx.Done():
				return nil, ctx.Err()
			}
			mu.Lock()
			active--
			mu.Unlock()
			return &pb.Product{Id: id, PriceUsd: usd(1, 0)}, nil
		}},
		currencySvcClient: currencyClient{
			convert: func(_ context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
				return &pb.Money{CurrencyCode: "EUR", Units: 1}, nil
			},
		},
	}
	if _, err := cs.prepOrderItems(context.Background(), cartItems("a", "b", "c", "d", "e"), "EUR"); err != nil {
		t.Fatal(err)
	}
	if maxActive > maxConcurrentOrderItemPreparations {
		t.Fatalf("max product calls = %d, want <= %d", maxActive, maxConcurrentOrderItemPreparations)
	}
}
