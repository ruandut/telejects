/** Telejects' price book (spec 0006): Rapid's shapes, as its price book page used them. */

/** Rapid's fixed provider numbers. */
export const PROVIDER = { vodacom: 0, mtn: 1, linkAfrica: 2, herotel: 3 } as const;

export type CatalogueProductRef = { id: number; name: string; provider_name: string };

export type AccessMediumRef = {
  id: number;
  name: string;
  provider_access_medium_identifier_id: number;
};

/** One price (Rapid's connect product definition). Money is a string; "-1.00" is on request. */
export type PriceDefinition = {
  id: number;
  name: string;
  provider: number;
  sublayer: number | null;
  access_medium: AccessMediumRef | null;
  product: CatalogueProductRef | null;
  connect_products: { id: number; name: string }[];
  duration: number;
  monthly_recurring_cost: string;
  none_recurring_cost: string;
  data_allocation: number | null;
  data_allocation_notes: string | null;
  max_bandwidth: number | null;
  max_upload_bandwidth: number | null;
  medium: string | null;
};

export type PriceDefinitionInput = {
  name: string;
  provider: number | null;
  sublayer: number | null;
  access_medium: number | null;
  product: number | null;
  connect_products: number[];
  duration: number;
  monthly_recurring_cost: string;
  none_recurring_cost: string;
  data_allocation: number | null;
  data_allocation_notes: string;
  max_bandwidth: number;
  max_upload_bandwidth: number;
  medium: string;
};

export type PricePage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: PriceDefinition[];
};

export type PriceFilters = {
  page: number;
  search: string;
  provider: number | null;
  medium: string;
};

/** A connect product, as "Manage products" lists it. */
export type BookConnectProduct = {
  id: number;
  name: string;
  description: string | null;
  definition_count: number;
};

export type ConnectProductInput = { name: string; description: string };

export type BookOptions = {
  providers: { value: number; label: string }[];
  sublayers: { value: number; label: string }[];
  mediums: string[];
  access_media: { id: number; name: string; identifier: number }[];
  products: { id: number; name: string; provider: number }[];
  /** Telejects staff keep the book; everyone else reads it. */
  can_edit: boolean;
};
